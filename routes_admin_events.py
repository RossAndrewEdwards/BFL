import csv
import io
import sqlite3
from collections import defaultdict
from datetime import datetime

from flask import Response


EVENT_STAT_FIELDS = [
    ("rounds_fought", "Rounds fought"),
    ("special_awards", "Special awards"),
    ("gold_medals", "Gold medals"),
    ("silver_medals", "Silver medals"),
    ("bronze_medals", "Bronze medals"),
    ("kills", "Kills"),
    ("assists", "Assists"),
    ("deaths", "Deaths"),
    ("sit_downs", "Sit downs"),
    ("yellow_cards", "Yellow cards"),
    ("red_cards", "Red cards"),
]

WORKSPACE_STAT_SHORT_LABELS = {
    "rounds_fought": "RF",
    "special_awards": "SA",
    "gold_medals": "G",
    "silver_medals": "S",
    "bronze_medals": "B",
    "kills": "K",
    "assists": "A",
    "deaths": "D",
    "sit_downs": "SD",
    "yellow_cards": "Y",
    "red_cards": "R",
}


def register_admin_event_routes(app, deps):
    from event_scoring_support import EventScoringCoordinator
    admin_required = deps["admin_required"]
    db = deps["db"]
    abort = deps["abort"]
    request = deps["request"]
    require_active_season_editable = deps["require_active_season_editable"]
    parse_int_field = deps["parse_int_field"]
    ValidationError = deps["ValidationError"]
    event_result_audit_state = deps["event_result_audit_state"]
    log_audit = deps["log_audit"]
    flash = deps["flash"]
    redirect = deps["redirect"]
    url_for = deps["url_for"]
    scheduled_event_rows = deps["scheduled_event_rows"]
    render_template = deps["render_template"]
    effective_league_id = deps["effective_league_id"]
    create_notification = deps["create_notification"]
    apply_collection_filters = deps["apply_collection_filters"]
    current_user = deps["current_user"]
    rules_dict = deps["rules_dict"]
    event_points = deps["event_points"]
    is_site_admin = deps["is_site_admin"]
    scoped_league_id = deps["scoped_league_id"]
    sync_calendar_event_banners = deps["sync_calendar_event_banners"]
    now_iso = deps.get("now_iso")

    event_export_fields = [
        "event_name",
        "event_date",
        "group_name",
        "entry_status",
        "fighter_name",
        "rounds_fought",
        "special_awards",
        "gold_medals",
        "silver_medals",
        "bronze_medals",
        "kills",
        "assists",
        "deaths",
        "sit_downs",
        "yellow_cards",
        "red_cards",
    ]

    def current_timestamp():
        return now_iso() if now_iso else None

    def workspace_stat_columns():
        return [
            {
                "key": key,
                "label": label,
                "short_label": WORKSPACE_STAT_SHORT_LABELS.get(key, label),
            }
            for key, label in EVENT_STAT_FIELDS
        ]

    def sync_calendar_if_needed(conn):
        synced_count = sync_calendar_event_banners(conn)
        if synced_count:
            conn.commit()
        return synced_count

    def scoped_event_result(conn, event_id):
        league_id = scoped_league_id(conn)
        return conn.execute(
            "SELECT * FROM event_results WHERE id=? AND (? IS NULL OR league_id=?)",
            (event_id, league_id, league_id),
        ).fetchone()

    def scoped_event_banner(conn, banner_id):
        league_id = scoped_league_id(conn)
        return conn.execute(
            "SELECT * FROM event_banners WHERE id=? AND (? IS NULL OR league_id=?)",
            (banner_id, league_id, league_id),
        ).fetchone()

    def scoped_fighters(conn):
        league_id = scoped_league_id(conn)
        return conn.execute(
            "SELECT id,name FROM fighters WHERE (? IS NULL OR league_id=?) ORDER BY name",
            (league_id, league_id),
        ).fetchall()

    def league_options(conn):
        return conn.execute("SELECT id, name FROM leagues ORDER BY name, id").fetchall()

    def selected_scope_league_id(conn):
        user = current_user()
        if not is_site_admin(user):
            return scoped_league_id(conn)
        raw = request.values.get("league_id", "").strip()
        if not raw:
            return None
        try:
            league_id = int(raw)
        except ValueError as exc:
            raise ValidationError("Choose a valid league.") from exc
        league = conn.execute("SELECT id FROM leagues WHERE id=?", (league_id,)).fetchone()
        if not league:
            raise ValidationError("Choose a valid league.")
        return league_id

    def selected_scope_league(conn):
        if not is_site_admin(current_user()):
            return None
        league_id = selected_scope_league_id(conn)
        if league_id is None:
            return None
        return conn.execute("SELECT id, name FROM leagues WHERE id=?", (league_id,)).fetchone()

    def selected_import_league_id(conn):
        user = current_user()
        if not is_site_admin(user):
            league_id = effective_league_id(conn)
            if not league_id:
                raise ValidationError("A target league is required for event imports.")
            return league_id
        raw = request.form.get("target_league_id", "").strip()
        if not raw:
            raise ValidationError("Choose a target league for the event import.")
        try:
            league_id = int(raw)
        except ValueError as exc:
            raise ValidationError("Choose a valid target league for the event import.") from exc
        league = conn.execute("SELECT id FROM leagues WHERE id=?", (league_id,)).fetchone()
        if not league:
            raise ValidationError("Choose a valid target league for the event import.")
        return league_id

    def mutation_league_id(conn, *, field_name="target_league_id", fallback_scope=True):
        if not is_site_admin(current_user()):
            league_id = effective_league_id(conn)
            if not league_id:
                raise ValidationError("A league context is required.")
            return league_id
        raw = request.form.get(field_name, "").strip()
        if raw:
            try:
                league_id = int(raw)
            except ValueError as exc:
                raise ValidationError("Choose a valid league.") from exc
            league = conn.execute("SELECT id FROM leagues WHERE id=?", (league_id,)).fetchone()
            if not league:
                raise ValidationError("Choose a valid league.")
            return league_id
        if fallback_scope:
            league_id = selected_scope_league_id(conn)
            if league_id is not None:
                return league_id
        raise ValidationError("Choose a league before starting event scoring.")

    def csv_response(filename, fieldnames, rows):
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    def imported_int(value, label, *, default=0, minimum=0):
        raw = str(value or "").strip()
        if raw == "":
            return default
        try:
            parsed = int(raw)
        except ValueError as exc:
            raise ValidationError(f"{label} must be a whole number.") from exc
        if parsed < minimum:
            raise ValidationError(f"{label} cannot be less than {minimum}.")
        return parsed

    def imported_text(row, key):
        return str(row.get(key, "") or "").strip()

    def stat_values_from_request():
        return {field: parse_int_field(field, default=0, minimum=0) for field, _ in EVENT_STAT_FIELDS}

    def ensure_fighter_in_league(conn, fighter_id, league_id):
        fighter = conn.execute(
            "SELECT id, name FROM fighters WHERE id=? AND league_id=?",
            (fighter_id, league_id),
        ).fetchone()
        if not fighter:
            raise ValidationError("Select a fighter from your league before saving results.")
        return fighter

    def get_or_create_event_banner(conn, league_id):
        raw_scheduled_event_id = request.form.get("scheduled_event_id", "").strip()
        if raw_scheduled_event_id:
            try:
                scheduled_event_id = int(raw_scheduled_event_id)
            except ValueError as exc:
                raise ValidationError("Choose a valid scheduled event.") from exc
            event_banner = conn.execute(
                "SELECT * FROM event_banners WHERE id=? AND league_id=?",
                (scheduled_event_id, league_id),
            ).fetchone()
            if not event_banner:
                raise ValidationError("Choose a valid scheduled event from your league.")
            return event_banner
        event_name = request.form.get("event_name", "").strip()
        event_date = request.form.get("event_date", "").strip()
        if not event_name:
            raise ValidationError("Event name is required when no scheduled event is selected.")
        if not event_date:
            raise ValidationError("Event date is required when no scheduled event is selected.")
        existing = conn.execute(
            """
            SELECT *
            FROM event_banners
            WHERE league_id=? AND event_name=? AND event_date=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (league_id, event_name, event_date),
        ).fetchone()
        if existing:
            return existing
        conn.execute(
            """
            INSERT INTO event_banners(league_id,event_name,event_date,source_kind)
            VALUES(?,?,?,'manual')
            """,
            (league_id, event_name, event_date),
        )
        banner_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        return conn.execute("SELECT * FROM event_banners WHERE id=?", (banner_id,)).fetchone()

    def group_rows(result_rows):
        grouped = defaultdict(list)
        for row in result_rows:
            key = row["group_name"] or "Ungrouped"
            grouped[key].append(row)
        groups = []
        for group_name in sorted(grouped.keys(), key=lambda value: (value == "Ungrouped", value.lower())):
            rows = grouped[group_name]
            groups.append(
                {
                    "name": group_name,
                    "rows": rows,
                    "draft_count": sum(1 for row in rows if row["entry_status"] == "draft"),
                    "complete_count": sum(1 for row in rows if row["entry_status"] == "complete"),
                }
            )
        return groups

    def remaining_fighters_for_event(fighters, result_rows):
        scored_fighter_ids = {row["fighter_id"] for row in result_rows}
        rows = [fighter for fighter in fighters if fighter["id"] not in scored_fighter_ids]
        rows.sort(key=lambda fighter: fighter["name"].lower())
        return rows

    def workspace_calendar_rows(conn, banner):
        banner_year = (banner["event_date"] or datetime.utcnow().date().isoformat())[:4]
        today_iso = datetime.utcnow().date().isoformat()
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT eb.*,
                       COUNT(er.id) AS result_count,
                       SUM(CASE WHEN er.entry_status='draft' THEN 1 ELSE 0 END) AS draft_result_count,
                       SUM(CASE WHEN er.entry_status='complete' THEN 1 ELSE 0 END) AS complete_result_count
                FROM event_banners eb
                LEFT JOIN event_results er ON er.scheduled_event_id = eb.id
                WHERE eb.league_id=?
                  AND eb.source_kind='calendar'
                  AND substr(eb.event_date, 1, 4)=?
                GROUP BY eb.id
                ORDER BY eb.event_date ASC, eb.event_name ASC
                """,
                (banner["league_id"], banner_year),
            ).fetchall()
        ]
        for row in rows:
            row["is_current"] = row["id"] == banner["id"]
            if row["event_date"] < today_iso:
                row["calendar_status"] = "Past"
            elif row["event_date"] == today_iso:
                row["calendar_status"] = "Today"
            else:
                row["calendar_status"] = "Upcoming"
            if row.get("draft_result_count"):
                row["scoring_status"] = "In Progress"
            elif row.get("complete_result_count"):
                row["scoring_status"] = "Scored"
            else:
                row["scoring_status"] = "Unscored"
        return banner_year, rows

    @app.route("/admin/events/<int:event_id>/edit", methods=["GET", "POST"])
    @admin_required
    def admin_event_edit(event_id):
        conn = db()
        sync_calendar_if_needed(conn)
        league_id = scoped_league_id(conn)
        row = scoped_event_result(conn, event_id)
        if not row:
            abort(404)
        if request.method == "POST":
            try:
                event_banner = get_or_create_event_banner(conn, row["league_id"] or league_id)
                fighter_id = parse_int_field("fighter_id", minimum=1)
                stats = stat_values_from_request()
                group_name = request.form.get("group_name", "").strip()
                entry_status = "complete" if request.form.get("entry_status") == "complete" else "draft"
                
                EventScoringCoordinator(conn).update_event_result(
                    event_id=event_id,
                    banner_id=event_banner["id"],
                    fighter_id=fighter_id,
                    stats=stats,
                    group_name=group_name,
                    entry_status=entry_status,
                )
                conn.commit()
                flash("Event result updated.")
                return redirect(url_for("admin_event_workspace", banner_id=event_banner["id"]))
            except ValidationError as exc:
                flash(str(exc))
                row = scoped_event_result(conn, event_id)
        scheduled_events = scheduled_event_rows(conn)
        fighters = scoped_fighters(conn)
        return render_template(
            "admin_event_form.html",
            row=row,
            scheduled_events=scheduled_events,
            fighters=fighters,
            stat_fields=EVENT_STAT_FIELDS,
        )

    @app.post("/admin/events/workspace/start")
    @admin_required
    def admin_event_workspace_start():
        conn = db()
        sync_calendar_if_needed(conn)
        try:
            league_id = mutation_league_id(conn, field_name="target_league_id")
            event_banner = get_or_create_event_banner(conn, league_id)
            conn.commit()
            return redirect(url_for("admin_event_workspace", banner_id=event_banner["id"]))
        except ValidationError as exc:
            flash(str(exc))
            return redirect(url_for("admin_events"))

    @app.route("/admin/events/workspace/<int:banner_id>", methods=["GET", "POST"])
    @admin_required
    def admin_event_workspace(banner_id):
        conn = db()
        sync_calendar_if_needed(conn)
        banner = scoped_event_banner(conn, banner_id)
        if not banner:
            abort(404)
        def load_workspace_rows():
            rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT er.*, f.name AS fighter_name
                    FROM event_results er
                    JOIN fighters f ON f.id = er.fighter_id
                    WHERE er.scheduled_event_id=?
                    ORDER BY COALESCE(er.group_name, ''), er.entry_status DESC, f.name
                    """,
                    (banner["id"],),
                ).fetchall()
            ]
            return rows
        if request.method == "POST":
            try:
                workspace_action = request.form.get("workspace_action", "").strip()
                group_name = request.form.get("group_name", "").strip()
                if workspace_action == "add_group_fighters":
                    EventScoringCoordinator(conn).add_fighters_to_group(
                        banner_id=banner["id"],
                        group_name=group_name,
                        fighter_ids=request.form.getlist("fighter_ids"),
                    )
                elif workspace_action == "save_group_scores":
                    group_result_rows = conn.execute(
                        """
                        SELECT er.id
                        FROM event_results er
                        WHERE er.scheduled_event_id=? AND COALESCE(er.group_name, '')=?
                        """,
                        (banner["id"], group_name),
                    ).fetchall()
                    if not group_result_rows:
                        raise ValidationError("That group does not have any fighters yet.")
                    score_payloads = {}
                    for row in group_result_rows:
                        rid = row["id"]
                        stats = {}
                        for field, _label in EVENT_STAT_FIELDS:
                            key = f"result_{rid}_{field}"
                            try:
                                stats[field] = int(str(request.form.get(key, "0")).strip() or "0")
                            except ValueError as exc:
                                f_name = conn.execute("SELECT f.name FROM event_results er JOIN fighters f ON f.id=er.fighter_id WHERE er.id=?", (rid,)).fetchone()["name"]
                                raise ValidationError(f"{f_name} has an invalid value for {field.replace('_', ' ')}.") from exc
                        score_payloads[rid] = stats
                    
                    entry_status = "complete" if request.form.get("submit_action") == "complete" else "draft"
                    EventScoringCoordinator(conn).save_group_scores(
                        banner_id=banner["id"],
                        group_name=group_name,
                        score_payloads=score_payloads,
                        entry_status=entry_status,
                    )
                else:
                    raise ValidationError("Choose a valid event workspace action.")
                create_notification(
                    conn,
                    "Event workspace updated",
                    f"{banner['event_name']} results were updated inside the live scoring workspace.",
                    "event",
                )
                conn.commit()
                flash("Event workspace updated.")
                next_group = group_name or ""
                return redirect(url_for("admin_event_workspace", banner_id=banner["id"], group_name=next_group))
            except ValidationError as exc:
                flash(str(exc))

        result_rows = load_workspace_rows()
        groups = group_rows(result_rows)
        fighters = [dict(row) for row in scoped_fighters(conn)]
        remaining_fighters = remaining_fighters_for_event(fighters, result_rows)
        distinct_fighters_with_results = len({row["fighter_id"] for row in result_rows})
        complete_count = sum(1 for row in result_rows if row["entry_status"] == "complete")
        draft_count = sum(1 for row in result_rows if row["entry_status"] == "draft")
        calendar_year, calendar_year_events = workspace_calendar_rows(conn, banner)
        context = {
            "banner": banner,
            "groups": groups,
            "fighters": fighters,
            "remaining_fighters": remaining_fighters,
            "selected_group_name": request.args.get("group_name", "").strip(),
            "stat_fields": EVENT_STAT_FIELDS,
            "workspace_stat_columns": workspace_stat_columns(),
            "total_fighters_in_league": len(fighters),
            "fighters_with_results": distinct_fighters_with_results,
            "complete_count": complete_count,
            "draft_count": draft_count,
            "calendar_year": calendar_year,
            "calendar_year_events": calendar_year_events,
        }
        return render_template("admin_event_workspace.html", **context)

    @app.route("/admin/events", methods=["GET", "POST"])
    @admin_required
    def admin_events():
        conn = db()
        sync_calendar_if_needed(conn)
        league_id = scoped_league_id(conn)
        selected_league = selected_scope_league(conn)
        if request.method == "POST":
            try:
                require_active_season_editable(conn, "Event result changes")
                target_league_id = mutation_league_id(conn)
                event_banner = get_or_create_event_banner(conn, target_league_id)
                fighter_id = parse_int_field("fighter_id", minimum=1)
                stats = stat_values_from_request()
                group_name = request.form.get("group_name", "").strip()
                entry_status = "complete" if request.form.get("submit_action") == "complete" else "draft"
                
                EventScoringCoordinator(conn).create_manual_result(
                    banner_id=event_banner["id"],
                    fighter_id=fighter_id,
                    stats=stats,
                    group_name=group_name,
                    entry_status=entry_status,
                )
                create_notification(conn, "New event result posted", f"{event_banner['event_name']} results were updated on {event_banner['event_date']}.", "event")
            except ValidationError as exc:
                flash(str(exc))
                return redirect(url_for("admin_events"))
            except sqlite3.IntegrityError:
                flash("That fighter could not be found.")
                return redirect(url_for("admin_events"))
            conn.commit()
            flash("Event result added.")
            return redirect(url_for("admin_events"))
        events = [
            dict(row)
            for row in conn.execute(
                """
                SELECT er.*, f.name AS fighter_name, eb.id AS linked_event_id, eb.source_kind
                FROM event_results er
                JOIN fighters f ON f.id = er.fighter_id
                LEFT JOIN event_banners eb ON eb.id = er.scheduled_event_id
                WHERE (? IS NULL OR er.league_id=?)
                ORDER BY er.event_date DESC, er.event_name, COALESCE(er.group_name, ''), f.name
                """,
                (league_id, league_id),
            ).fetchall()
        ]
        if selected_league:
            events = [row for row in events if row.get("league_id") == selected_league["id"]]
        scheduled_event_options = scheduled_event_rows(conn)
        if selected_league:
            scheduled_event_options = [row for row in scheduled_event_options if row.get("league_id") == selected_league["id"]]
        scheduled_lookup = {row["id"]: row for row in scheduled_event_options}
        for row in events:
            row["season"] = row["event_date"][:4]
            linked = scheduled_lookup.get(row.get("scheduled_event_id"))
            row["scheduled_status_label"] = linked["status_label"] if linked else "Manual"
        fighters = scoped_fighters(conn)
        fighter_options = [{"value": str(fighter["name"]), "label": fighter["name"]} for fighter in fighters]
        events, toolbar = apply_collection_filters(
            events,
            search_fields=["event_name", "fighter_name", "event_date", "season", "group_name"],
            filters=[
                {"name": "fighter", "label": "Fighter", "field": "fighter_name", "options": fighter_options},
                {"name": "season", "label": "Season", "field": "season"},
                {"name": "status", "label": "Entry Status", "field": "entry_status"},
            ],
            sort_options=[
                {"value": "default", "label": "Latest Results"},
                {"value": "event", "label": "Event Name (A-Z)", "key": lambda row: row["event_name"]},
                {"value": "fighter_name", "label": "Fighter (A-Z)", "key": lambda row: row["fighter_name"]},
            ],
            search_placeholder="Search event names, fighters, dates, groups, or seasons",
        )
        return render_template(
            "admin_events.html",
            events=events,
            fighters=fighters,
            scheduled_events=scheduled_event_options,
            rules=rules_dict(conn),
            event_points=event_points,
            toolbar=toolbar,
            league_options=league_options(conn),
            can_choose_import_league=is_site_admin(current_user()),
            selected_scope_league=selected_league,
            stat_fields=EVENT_STAT_FIELDS,
        )

    @app.route("/admin/events/export.csv")
    @admin_required
    def admin_events_export():
        conn = db()
        sync_calendar_if_needed(conn)
        league_id = selected_scope_league_id(conn)
        rows = conn.execute(
            """
            SELECT
                er.event_name,
                er.event_date,
                COALESCE(er.group_name, '') AS group_name,
                er.entry_status,
                f.name AS fighter_name,
                er.rounds_fought,
                er.special_awards,
                er.gold_medals,
                er.silver_medals,
                er.bronze_medals,
                er.kills,
                er.assists,
                er.deaths,
                er.sit_downs,
                er.yellow_cards,
                er.red_cards
            FROM event_results er
            JOIN fighters f ON f.id = er.fighter_id
            WHERE (? IS NULL OR er.league_id=?)
            ORDER BY er.event_date DESC, er.event_name, COALESCE(er.group_name, ''), f.name
            """,
            (league_id, league_id),
        ).fetchall()
        filename = "event-results.csv" if league_id is None else f"league-{league_id}-event-results.csv"
        return csv_response(filename, event_export_fields, [dict(row) for row in rows])

    @app.post("/admin/events/import")
    @admin_required
    def admin_events_import():
        conn = db()
        sync_calendar_if_needed(conn)
        try:
            target_league_id = selected_import_league_id(conn)
            payload = request.form.get("csv_payload", "").strip()
            if not payload:
                raise ValidationError("Paste CSV data to import event results.")
            reader = csv.DictReader(io.StringIO(payload))
            required_fields = {"event_name", "event_date", "fighter_name"}
            if not reader.fieldnames or not required_fields.issubset(set(reader.fieldnames)):
                raise ValidationError("Event import CSV must include event_name, event_date, and fighter_name columns.")
            created_count = 0
            updated_count = 0
            for row in reader:
                if not any(str(value or "").strip() for value in row.values()):
                    continue
                event_name = imported_text(row, "event_name")
                event_date = imported_text(row, "event_date")
                fighter_name = imported_text(row, "fighter_name")
                if not event_name or not event_date or not fighter_name:
                    raise ValidationError("Each event row must include event_name, event_date, and fighter_name.")
                scheduled_event = conn.execute(
                    """
                    SELECT id, event_name, event_date
                    FROM event_banners
                    WHERE league_id=? AND event_name=? AND event_date=?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (target_league_id, event_name, event_date),
                ).fetchone()
                if not scheduled_event:
                    conn.execute(
                        """
                        INSERT INTO event_banners(league_id,event_name,event_date,source_kind)
                        VALUES(?,?,?,'manual')
                        """,
                        (target_league_id, event_name, event_date),
                    )
                    scheduled_event = conn.execute(
                        "SELECT * FROM event_banners WHERE id=last_insert_rowid()"
                    ).fetchone()
                fighter = conn.execute(
                    "SELECT id FROM fighters WHERE league_id=? AND name=?",
                    (target_league_id, fighter_name),
                ).fetchone()
                if not fighter:
                    raise ValidationError(f"Fighter not found in this league: {fighter_name}.")
                result_values = (
                    scheduled_event["id"],
                    scheduled_event["event_date"],
                    scheduled_event["event_name"],
                    fighter["id"],
                    target_league_id,
                    imported_text(row, "group_name") or None,
                    imported_text(row, "entry_status").lower() if imported_text(row, "entry_status").lower() in {"draft", "complete"} else "complete",
                    current_timestamp(),
                    imported_int(row.get("rounds_fought"), "Rounds fought", default=0, minimum=0),
                    imported_int(row.get("special_awards"), "Special awards", default=0, minimum=0),
                    imported_int(row.get("gold_medals"), "Gold medals", default=0, minimum=0),
                    imported_int(row.get("silver_medals"), "Silver medals", default=0, minimum=0),
                    imported_int(row.get("bronze_medals"), "Bronze medals", default=0, minimum=0),
                    imported_int(row.get("kills"), "Kills", default=0, minimum=0),
                    imported_int(row.get("assists"), "Assists", default=0, minimum=0),
                    imported_int(row.get("deaths"), "Deaths", default=0, minimum=0),
                    imported_int(row.get("sit_downs"), "Sit downs", default=0, minimum=0),
                    imported_int(row.get("yellow_cards"), "Yellow cards", default=0, minimum=0),
                    imported_int(row.get("red_cards"), "Red cards", default=0, minimum=0),
                )
                existing = conn.execute(
                    """
                    SELECT id
                    FROM event_results
                    WHERE league_id=? AND scheduled_event_id=? AND fighter_id=?
                    """,
                    (target_league_id, scheduled_event["id"], fighter["id"]),
                ).fetchone()
                if existing:
                    conn.execute(
                        """
                        UPDATE event_results
                        SET scheduled_event_id=?, event_date=?, event_name=?, fighter_id=?, league_id=?,
                            group_name=?, entry_status=?, updated_at=?, rounds_fought=?, special_awards=?, gold_medals=?, silver_medals=?,
                            bronze_medals=?, kills=?, assists=?, deaths=?, sit_downs=?,
                            yellow_cards=?, red_cards=?
                        WHERE id=?
                        """,
                        result_values + (existing["id"],),
                    )
                    updated_count += 1
                else:
                    conn.execute(
                        """
                        INSERT INTO event_results(
                            scheduled_event_id,event_date,event_name,fighter_id,league_id,group_name,entry_status,updated_at,
                            rounds_fought,special_awards,gold_medals,silver_medals,bronze_medals,
                            kills,assists,deaths,sit_downs,yellow_cards,red_cards
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        result_values,
                    )
                    created_count += 1
            if created_count == 0 and updated_count == 0:
                raise ValidationError("No event result rows were found in the CSV payload.")
            log_audit(
                conn,
                "league",
                target_league_id,
                "bulk_import",
                f"Imported event results into league {target_league_id}.",
                after_state={"created_count": created_count, "updated_count": updated_count},
                league_id=target_league_id,
            )
            conn.commit()
            flash(f"Event import complete. Created {created_count}, updated {updated_count}.")
        except ValidationError as exc:
            flash(str(exc))
        except sqlite3.IntegrityError:
            flash("One or more event rows could not be imported.")
        return redirect(url_for("admin_events"))

    @app.post("/admin/events/<int:event_id>/delete")
    @admin_required
    def admin_event_delete(event_id):
        conn = db()
        try:
            require_active_season_editable(conn, "Event result changes")
        except ValidationError as exc:
            flash(str(exc))
            return redirect(url_for("admin_events"))
        row = scoped_event_result(conn, event_id)
        if not row:
            abort(404)
        before = event_result_audit_state(conn, event_id)
        banner_id = row["scheduled_event_id"]
        conn.execute("DELETE FROM event_results WHERE id=?", (event_id,))
        log_audit(conn, "event_result", event_id, "delete", "Deleted an event result row.", before_state=before, rollback_type="event_delete")
        create_notification(conn, "Event result removed", "An event result row was removed by an admin.", "warning")
        conn.commit()
        flash("Event result deleted.")
        if banner_id:
            return redirect(url_for("admin_event_workspace", banner_id=banner_id))
        return redirect(url_for("admin_events"))
