import csv
import datetime
import io
import json
import sqlite3
from flask import Response


def register_admin_fighter_routes(app, deps):
    from src.support.training import TrainingHonoursEngine
    from src.support.fighter_request import FighterRequestEngine
    admin_required = deps["admin_required"]
    db = deps["db"]
    leaderboard_rows = deps["leaderboard_rows"]
    apply_collection_filters = deps["apply_collection_filters"]
    current_season = deps["current_season"]
    current_user = deps["current_user"]
    ensure_active_season = deps["ensure_active_season"]
    is_site_admin = deps["is_site_admin"]
    render_template = deps["render_template"]
    abort = deps["abort"]
    require_active_season_editable = deps["require_active_season_editable"]
    attendance_score_form_values = deps["attendance_score_form_values"]
    log_audit = deps["log_audit"]
    flash = deps["flash"]
    redirect = deps["redirect"]
    url_for = deps["url_for"]
    ValidationError = deps["ValidationError"]
    fighter_form_values = deps["fighter_form_values"]
    fighter_baseline_values = deps["fighter_baseline_values"]
    effective_league_id = deps["effective_league_id"]
    scoped_league_id = deps["scoped_league_id"]
    submitted_fighter_form = deps["submitted_fighter_form"]
    submitted_baseline = deps["submitted_baseline"]
    fighter_admin_totals = deps["fighter_admin_totals"]
    request = deps["request"]

    fighter_export_fields = [
        "name",
        "tier",
        "current_cost",
        "training",
        "support",
        "age",
        "height",
        "weight",
        "nickname",
        "fighting_style",
        "preferred_role",
        "role_or_weapon",
        "known_for",
        "why_buhurt",
        "joined_year",
        "reputation",
        "notes",
        "image_url",
        "image_credit",
        "image_source_url",
        "bio",
        "hero_quote",
    ]

    honour_type_options = [
        ("special_awards", "Special Award"),
        ("gold_medals", "Gold Medal"),
        ("silver_medals", "Silver Medal"),
        ("bronze_medals", "Bronze Medal"),
    ]

    def scoped_fighter(conn, fighter_id, fields="*"):
        league_id = scoped_league_id(conn)
        return conn.execute(
            f"SELECT {fields} FROM fighters WHERE id=? AND (? IS NULL OR league_id=?)",
            (fighter_id, league_id, league_id),
        ).fetchone()

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

    def workspace_league_id(conn):
        if is_site_admin(current_user()):
            return selected_scope_league_id(conn)
        return effective_league_id(conn)

    def workspace_league(conn):
        league_id = workspace_league_id(conn)
        if not league_id:
            return None
        return conn.execute("SELECT id, name FROM leagues WHERE id=?", (league_id,)).fetchone()

    def training_workspace_fighters(conn, league_id):
        return conn.execute(
            """
            SELECT
                f.id,
                f.name,
                f.nickname,
                f.tier,
                COALESCE(bs.training, 0) AS training,
                COALESCE(bs.support, 0) AS support
            FROM fighters f
            LEFT JOIN baseline_stats bs ON bs.fighter_id = f.id
            WHERE f.league_id=?
            ORDER BY f.name, f.id
            """,
            (league_id,),
        ).fetchall()

    def honour_rows(conn, league_id):
        return conn.execute(
            """
            SELECT fh.*, f.name AS fighter_name
            FROM fighter_honours fh
            JOIN fighters f ON f.id = fh.fighter_id
            WHERE fh.league_id=?
            ORDER BY fh.awarded_on DESC, fh.id DESC
            """,
            (league_id,),
        ).fetchall()

    def scoped_training_group(conn, group_id):
        league_id = workspace_league_id(conn)
        if not league_id:
            return None
        return conn.execute(
            """
            SELECT *
            FROM training_groups
            WHERE id=? AND league_id=?
            """,
            (group_id, league_id),
        ).fetchone()

    # Legacy validate_group_fighter_ids and apply_attendance_increment have been consolidated into TrainingHonoursEngine.

    def selected_import_league_id(conn):
        user = current_user()
        if not is_site_admin(user):
            league_id = effective_league_id(conn)
            if not league_id:
                raise ValidationError("A target league is required for imports.")
            return league_id
        raw = request.form.get("target_league_id", "").strip()
        if not raw:
            raise ValidationError("Choose a target league for the fighter import.")
        try:
            league_id = int(raw)
        except ValueError as exc:
            raise ValidationError("Choose a valid target league for the fighter import.") from exc
        league = conn.execute("SELECT id FROM leagues WHERE id=?", (league_id,)).fetchone()
        if not league:
            raise ValidationError("Choose a valid target league for the fighter import.")
        return league_id

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

    def scoped_request(conn, request_id):
        league_id = scoped_league_id(conn)
        return conn.execute(
            """
            SELECT fcr.*, u.display_name AS requester_name, rv.display_name AS reviewer_name, f.name AS fighter_name, l.name AS league_name
            FROM fighter_change_requests fcr
            JOIN users u ON u.id = fcr.requester_user_id
            LEFT JOIN users rv ON rv.id = fcr.reviewed_by_user_id
            LEFT JOIN fighters f ON f.id = fcr.fighter_id
            LEFT JOIN leagues l ON l.id = fcr.league_id
            WHERE fcr.id=? AND (? IS NULL OR fcr.league_id=?)
            """,
            (request_id, league_id, league_id),
        ).fetchone()

    @app.route("/admin/fighters")
    @admin_required
    def admin_fighters():
        conn = db()
        selected_league = selected_scope_league(conn)
        rows = leaderboard_rows(conn)
        if selected_league:
            rows = [row for row in rows if row.get("league_id") == selected_league["id"]]
        rows, toolbar = apply_collection_filters(
            rows,
            search_fields=["name", "nickname", "preferred_role", "fighting_style", "tier", "notes", "bio"],
            filters=[
                {"name": "tier", "label": "Tier", "field": "tier"},
            ],
            sort_options=[
                {"value": "default", "label": "Rank"},
                {"value": "name", "label": "Name (A-Z)", "key": lambda row: row["name"]},
                {"value": "cost", "label": "Cost (High-Low)", "key": lambda row: row["current_cost"], "reverse": True},
                {"value": "total", "label": "Total Points (High-Low)", "key": lambda row: row["total_points"], "reverse": True},
            ],
            search_placeholder="Search fighters, tiers, roles, or notes",
        )
        season = current_season(conn) or ensure_active_season(conn)
        return render_template(
            "admin_fighters.html",
            rows=rows,
            toolbar=toolbar,
            quick_attendance_date=datetime.datetime.utcnow().date().isoformat(),
            quick_attendance_season=season,
            league_options=league_options(conn),
            can_choose_import_league=is_site_admin(current_user()),
            selected_scope_league=selected_league,
        )

    @app.route("/admin/fighter-requests")
    @admin_required
    def admin_fighter_requests():
        conn = db()
        selected_league = selected_scope_league(conn)
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT fcr.*, u.display_name AS requester_name, rv.display_name AS reviewer_name, f.name AS fighter_name, l.name AS league_name
                FROM fighter_change_requests fcr
                JOIN users u ON u.id = fcr.requester_user_id
                LEFT JOIN users rv ON rv.id = fcr.reviewed_by_user_id
                LEFT JOIN fighters f ON f.id = fcr.fighter_id
                LEFT JOIN leagues l ON l.id = fcr.league_id
                WHERE (? IS NULL OR fcr.league_id=?)
                ORDER BY
                    CASE fcr.status
                        WHEN 'pending' THEN 0
                        WHEN 'approved' THEN 1
                        ELSE 2
                    END,
                    fcr.id DESC
                """,
                (selected_league["id"], selected_league["id"]) if selected_league else (None, None),
            ).fetchall()
        ]
        for row in rows:
            row["payload"] = json.loads(row["payload_json"])
            row["request_target"] = row["fighter_name"] or row["payload"].get("name") or "New fighter"
        rows, toolbar = apply_collection_filters(
            rows,
            search_fields=["requester_name", "fighter_name", "request_target", "league_name", "status", "request_type"],
            filters=[
                {"name": "status", "label": "Status", "field": "status"},
                {"name": "type", "label": "Type", "field": "request_type"},
            ],
            sort_options=[
                {"value": "default", "label": "Pending First"},
                {"value": "latest", "label": "Latest First", "key": lambda row: row["id"], "reverse": True},
            ],
            search_placeholder="Search requests, fighters, requesters, or leagues",
        )
        return render_template(
            "admin_fighter_requests.html",
            rows=rows,
            toolbar=toolbar,
            selected_scope_league=selected_league,
        )

    @app.route("/admin/training")
    @admin_required
    def admin_training_workspace():
        conn = db()
        league = workspace_league(conn)
        groups = []
        fighters = []
        if league:
            fighters = [dict(row) for row in training_workspace_fighters(conn, league["id"])]
            fighter_lookup = {row["id"]: row for row in fighters}
            raw_groups = conn.execute(
                """
                SELECT tg.*, COUNT(tgm.id) AS fighter_count
                FROM training_groups tg
                LEFT JOIN training_group_members tgm ON tgm.training_group_id = tg.id
                WHERE tg.league_id=?
                GROUP BY tg.id
                ORDER BY tg.sort_order, tg.name, tg.id
                """,
                (league["id"],),
            ).fetchall()
            for raw_group in raw_groups:
                members = []
                member_rows = conn.execute(
                    """
                    SELECT tgm.fighter_id, tgm.position
                    FROM training_group_members tgm
                    WHERE tgm.training_group_id=?
                    ORDER BY tgm.position, tgm.id
                    """,
                    (raw_group["id"],),
                ).fetchall()
                for member_row in member_rows:
                    fighter = fighter_lookup.get(member_row["fighter_id"])
                    if fighter:
                        members.append(fighter)
                groups.append(
                    {
                        "id": raw_group["id"],
                        "name": raw_group["name"],
                        "notes": raw_group["notes"] or "",
                        "fighter_count": raw_group["fighter_count"],
                        "members": members,
                    }
                )
        return render_template(
            "admin_training_workspace.html",
            league=league,
            groups=groups,
            fighters=fighters,
            quick_attendance_date=datetime.datetime.utcnow().date().isoformat(),
            league_options=league_options(conn),
            selected_scope_league=selected_scope_league(conn),
            can_choose_league=is_site_admin(current_user()),
        )

    @app.route("/admin/fighters/awards", methods=["GET", "POST"])
    @admin_required
    def admin_fighter_awards():
        conn = db()
        league = workspace_league(conn)
        if request.method == "POST":
            try:
                fighter_id = int(request.form.get("fighter_id", "").strip())
            except ValueError:
                fighter_id = 0
            fighter = scoped_fighter(conn, fighter_id, fields="id, name, league_id")
            if fighter and not league:
                league = conn.execute("SELECT id, name FROM leagues WHERE id=?", (fighter["league_id"],)).fetchone()
            if not fighter and is_site_admin(current_user()) and fighter_id:
                fighter = conn.execute(
                    "SELECT id, name, league_id FROM fighters WHERE id=?",
                    (fighter_id,),
                ).fetchone()
                if fighter:
                    league = conn.execute("SELECT id, name FROM leagues WHERE id=?", (fighter["league_id"],)).fetchone()
            try:
                if not league:
                    raise ValidationError("Choose a league before recording an award.")
                if not fighter:
                    raise ValidationError("Choose a fighter from this league.")
                honour_type = request.form.get("honour_type", "").strip()
                awarded_on = request.form.get("awarded_on", "").strip() or datetime.datetime.utcnow().date().isoformat()
                units = imported_int(request.form.get("units"), "Units", default=1, minimum=1)
                title = request.form.get("title", "").strip()
                notes = request.form.get("notes", "").strip()
                
                TrainingHonoursEngine(conn).record_honour(
                    league_id=league["id"],
                    fighter_id=fighter_id,
                    honour_type=honour_type,
                    units=units,
                    title=title,
                    notes=notes,
                    awarded_on=awarded_on,
                )
                conn.commit()
                flash("Award recorded.")
                return redirect(url_for("admin_fighter_awards", league_id=league["id"] if is_site_admin(current_user()) else None))
            except ValidationError as exc:
                flash(str(exc))
                honours = honour_rows(conn, league["id"]) if league else []
                fighters = training_workspace_fighters(conn, league["id"]) if league else []
                return render_template(
                    "admin_fighter_awards.html",
                    league=league,
                    honours=honours,
                    fighters=fighters,
                    honour_type_options=honour_type_options,
                    today=datetime.datetime.utcnow().date().isoformat(),
                    league_options=league_options(conn),
                    selected_scope_league=selected_scope_league(conn),
                    can_choose_league=is_site_admin(current_user()),
                ), 400
        honours = honour_rows(conn, league["id"]) if league else []
        fighters = training_workspace_fighters(conn, league["id"]) if league else []
        return render_template(
            "admin_fighter_awards.html",
            league=league,
            honours=honours,
            fighters=fighters,
            honour_type_options=honour_type_options,
            today=datetime.datetime.utcnow().date().isoformat(),
            league_options=league_options(conn),
            selected_scope_league=selected_scope_league(conn),
            can_choose_league=is_site_admin(current_user()),
        )

    @app.post("/admin/training/groups")
    @admin_required
    def admin_training_group_create():
        conn = db()
        league = workspace_league(conn)
        if not league:
            flash("Choose a league before creating a training group.")
            return redirect(url_for("admin_training_workspace"))
        name = request.form.get("name", "").strip()
        notes = request.form.get("notes", "").strip()
        try:
            TrainingHonoursEngine(conn).create_group(
                league_id=league["id"],
                name=name,
                notes=notes,
                fighter_ids=request.form.getlist("fighter_ids")
            )
            conn.commit()
            flash(f"Training group {name} created.")
        except ValidationError as exc:
            flash(str(exc))
        except sqlite3.IntegrityError:
            flash("A training group with that name already exists in this league.")
        return redirect(url_for("admin_training_workspace", league_id=league["id"] if is_site_admin(current_user()) else None))

    @app.post("/admin/training/groups/<int:group_id>/members")
    @admin_required
    def admin_training_group_members(group_id):
        conn = db()
        group = scoped_training_group(conn, group_id)
        if not group:
            abort(404)
        try:
            TrainingHonoursEngine(conn).update_group_members(
                group_id=group_id,
                fighter_ids=request.form.getlist("fighter_ids")
            )
            conn.commit()
            flash(f"Updated members for {group['name']}.")
        except ValidationError as exc:
            flash(str(exc))
        return redirect(url_for("admin_training_workspace", league_id=group["league_id"] if is_site_admin(current_user()) else None))

    @app.post("/admin/training/groups/<int:group_id>/delete")
    @admin_required
    def admin_training_group_delete(group_id):
        conn = db()
        group = scoped_training_group(conn, group_id)
        if not group:
            abort(404)
        try:
            TrainingHonoursEngine(conn).delete_group(group_id)
            conn.commit()
            flash(f"Deleted training group {group['name']}.")
        except ValidationError as exc:
            flash(str(exc))
        return redirect(url_for("admin_training_workspace", league_id=group["league_id"] if is_site_admin(current_user()) else None))

    @app.post("/admin/training/groups/<int:group_id>/mark")
    @admin_required
    def admin_training_group_mark(group_id):
        conn = db()
        group = scoped_training_group(conn, group_id)
        if not group:
            abort(404)
        try:
            payload = attendance_score_form_values(conn)
            count = TrainingHonoursEngine(conn).mark_attendance(group_id, payload)
            conn.commit()
            flash(f"{payload['score_type'].title()} added for {count} fighters in {group['name']}.")
        except ValidationError as exc:
            flash(str(exc))
        return redirect(url_for("admin_training_workspace", league_id=group["league_id"] if is_site_admin(current_user()) else None))

    @app.post("/admin/training/groups/<int:group_id>/fighters/<int:fighter_id>/mark")
    @admin_required
    def admin_training_group_fighter_mark(group_id, fighter_id):
        conn = db()
        group = scoped_training_group(conn, group_id)
        if not group:
            abort(404)
        fighter = conn.execute(
            """
            SELECT f.id, f.name, f.league_id
            FROM training_group_members tgm
            JOIN fighters f ON f.id = tgm.fighter_id
            WHERE tgm.training_group_id=? AND f.id=?
            """,
            (group_id, fighter_id),
        ).fetchone()
        if not fighter:
            abort(404)
        try:
            payload = attendance_score_form_values(conn)
            TrainingHonoursEngine(conn).mark_fighter_attendance(
                fighter_id=fighter_id,
                payload=payload,
                source=f"training_workspace_fighter:{group['name']}"
            )
            conn.commit()
            flash(f"{payload['score_type'].title()} added for {fighter['name']}.")
        except ValidationError as exc:
            flash(str(exc))
        return redirect(url_for("admin_training_workspace", league_id=group["league_id"] if is_site_admin(current_user()) else None))

    @app.post("/admin/fighter-requests/<int:request_id>/approve")
    @admin_required
    def admin_fighter_request_approve(request_id):
        conn = db()
        row = scoped_request(conn, request_id)
        if not row:
            abort(404)
        reviewer = current_user()
        review_notes = request.form.get("review_notes", "").strip() or None
        try:
            FighterRequestEngine(conn).approve_proposal(
                request_id=request_id,
                reviewer_id=reviewer["id"],
                review_notes=review_notes,
            )
            conn.commit()
            flash("Fighter request approved.")
        except ValidationError as exc:
            flash(str(exc))
        return redirect(url_for("admin_fighter_requests"))

    @app.post("/admin/fighter-requests/<int:request_id>/deny")
    @admin_required
    def admin_fighter_request_deny(request_id):
        conn = db()
        row = scoped_request(conn, request_id)
        if not row:
            abort(404)
        reviewer = current_user()
        review_notes = request.form.get("review_notes", "").strip() or None
        try:
            FighterRequestEngine(conn).deny_proposal(
                request_id=request_id,
                reviewer_id=reviewer["id"],
                review_notes=review_notes,
            )
            conn.commit()
            flash("Fighter request denied.")
        except ValidationError as exc:
            flash(str(exc))
        return redirect(url_for("admin_fighter_requests"))

    @app.route("/admin/fighters/export.csv")
    @admin_required
    def admin_fighters_export():
        conn = db()
        league_id = selected_scope_league_id(conn)
        rows = conn.execute(
            """
            SELECT
                f.name,
                f.tier,
                f.current_cost,
                COALESCE(bs.training, 0) AS training,
                COALESCE(bs.support, 0) AS support,
                f.age,
                f.height,
                f.weight,
                f.nickname,
                f.fighting_style,
                f.preferred_role,
                f.role_or_weapon,
                f.known_for,
                f.why_buhurt,
                f.joined_year,
                f.reputation,
                f.notes,
                f.image_url,
                f.image_credit,
                f.image_source_url,
                f.bio,
                f.hero_quote
            FROM fighters f
            LEFT JOIN baseline_stats bs ON bs.fighter_id = f.id
            WHERE (? IS NULL OR f.league_id=?)
            ORDER BY f.name
            """,
            (league_id, league_id),
        ).fetchall()
        filename = "fighters.csv" if league_id is None else f"league-{league_id}-fighters.csv"
        return csv_response(filename, fighter_export_fields, [dict(row) for row in rows])

    @app.post("/admin/fighters/import")
    @admin_required
    def admin_fighters_import():
        conn = db()
        try:
            target_league_id = selected_import_league_id(conn)
            payload = request.form.get("csv_payload", "").strip()
            if not payload:
                raise ValidationError("Paste CSV data to import fighters.")
            reader = csv.DictReader(io.StringIO(payload))
            if not reader.fieldnames or "name" not in reader.fieldnames:
                raise ValidationError("Fighter import CSV must include a name column.")
            created_count = 0
            updated_count = 0
            for row in reader:
                if not any(str(value or "").strip() for value in row.values()):
                    continue
                name = imported_text(row, "name")
                if not name:
                    raise ValidationError("Each fighter row must include a name.")
                tier = imported_text(row, "tier") or "A"
                current_cost = imported_int(row.get("current_cost"), "Current cost", default=100, minimum=0)
                baseline_training = imported_int(row.get("training"), "Training", default=0, minimum=0)
                baseline_support = imported_int(row.get("support"), "Support", default=0, minimum=0)
                fighter_values = (
                    name,
                    tier,
                    imported_int(row.get("age"), "Age", default=0, minimum=0) if imported_text(row, "age") else None,
                    imported_text(row, "height") or None,
                    imported_text(row, "weight") or None,
                    current_cost,
                    imported_text(row, "notes") or None,
                    imported_text(row, "nickname") or None,
                    imported_text(row, "fighting_style") or None,
                    imported_text(row, "preferred_role") or None,
                    imported_text(row, "role_or_weapon") or None,
                    imported_text(row, "known_for") or None,
                    imported_text(row, "why_buhurt") or None,
                    imported_int(row.get("joined_year"), "Joined year", default=0, minimum=0) if imported_text(row, "joined_year") else None,
                    imported_text(row, "reputation") or None,
                    imported_text(row, "image_url") or None,
                    imported_text(row, "image_credit") or None,
                    imported_text(row, "image_source_url") or None,
                    imported_text(row, "bio") or None,
                    imported_text(row, "hero_quote") or None,
                )
                existing = conn.execute(
                    "SELECT id FROM fighters WHERE league_id=? AND name=?",
                    (target_league_id, name),
                ).fetchone()
                if existing:
                    conn.execute(
                        """
                        UPDATE fighters
                        SET name=?, tier=?, age=?, height=?, weight=?, current_cost=?, notes=?, nickname=?,
                            fighting_style=?, preferred_role=?, role_or_weapon=?, known_for=?, why_buhurt=?, joined_year=?, reputation=?, image_url=?, image_credit=?,
                            image_source_url=?, bio=?, hero_quote=?
                        WHERE id=?
                        """,
                        fighter_values + (existing["id"],),
                    )
                    fighter_id = existing["id"]
                    updated_count += 1
                else:
                    conn.execute(
                        """
                        INSERT INTO fighters(
                            name, tier, age, height, weight, current_cost, notes, nickname, fighting_style,
                            preferred_role, role_or_weapon, known_for, why_buhurt, joined_year, reputation,
                            image_url, image_credit, image_source_url, bio, hero_quote, league_id
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        fighter_values + (target_league_id,),
                    )
                    fighter_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
                    created_count += 1
                conn.execute(
                    """
                    INSERT INTO baseline_stats(fighter_id,training,support)
                    VALUES(?,?,?)
                    ON CONFLICT(fighter_id) DO UPDATE SET
                        training=excluded.training,
                        support=excluded.support
                    """,
                    (fighter_id, baseline_training, baseline_support),
                )
            if created_count == 0 and updated_count == 0:
                raise ValidationError("No fighter rows were found in the CSV payload.")
            log_audit(
                conn,
                "league",
                target_league_id,
                "bulk_import",
                f"Imported fighters into league {target_league_id}.",
                after_state={"created_count": created_count, "updated_count": updated_count},
                league_id=target_league_id,
            )
            conn.commit()
            flash(f"Fighter import complete. Created {created_count}, updated {updated_count}.")
        except ValidationError as exc:
            flash(str(exc))
        except sqlite3.IntegrityError:
            flash("One or more fighter rows could not be imported.")
        return redirect(url_for("admin_fighters"))

    @app.post("/admin/fighters/<int:fighter_id>/attendance")
    @admin_required
    def admin_fighter_attendance(fighter_id):
        conn = db()
        fighter = scoped_fighter(conn, fighter_id, fields="id, name, league_id")
        if not fighter:
            abort(404)
        try:
            payload = attendance_score_form_values(conn)
            TrainingHonoursEngine(conn).mark_fighter_attendance(
                fighter_id=fighter_id,
                payload=payload,
                source="quick_admin_adjustment",
            )
            conn.commit()
            flash(f"{payload['score_type'].title()} added for {fighter['name']}.")
        except ValidationError as exc:
            flash(str(exc))
        return redirect(url_for("admin_fighters"))

    @app.route("/admin/fighters/new", methods=["GET", "POST"])
    @admin_required
    def admin_fighter_new():
        if request.method == "POST":
            conn = db()
            try:
                fighter_values = fighter_form_values()
                baseline = fighter_baseline_values()
                conn.execute(
                    "INSERT INTO fighters(name,tier,age,height,weight,current_cost,notes,nickname,fighting_style,preferred_role,role_or_weapon,known_for,why_buhurt,joined_year,reputation,image_url,image_credit,image_source_url,bio,hero_quote,league_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    fighter_values + (effective_league_id(conn),)
                )
                fid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
                conn.execute(
                    "INSERT INTO baseline_stats(fighter_id,training,support) VALUES(?,?,?)",
                    (fid, baseline["training"], baseline["support"])
                )
                log_audit(conn, "fighter", fid, "create", f"Added fighter {fighter_values[0]}.")
            except ValidationError as exc:
                flash(str(exc))
                return render_template("admin_fighter_form.html", fighter=submitted_fighter_form(), baseline=submitted_baseline({"training": 0, "support": 0})), 400
            except sqlite3.IntegrityError:
                flash("A fighter with that name already exists.")
                return render_template("admin_fighter_form.html", fighter=submitted_fighter_form(), baseline=submitted_baseline({"training": 0, "support": 0})), 400
            conn.commit()
            flash("Fighter added.")
            return redirect(url_for("admin_fighters"))
        return render_template("admin_fighter_form.html", fighter=None, baseline={"training": 0, "support": 0})

    @app.route("/admin/fighters/<int:fighter_id>", methods=["GET", "POST"])
    @admin_required
    def admin_fighter_edit(fighter_id):
        conn = db()
        fighter = scoped_fighter(conn, fighter_id)
        if not fighter:
            abort(404)
        if request.method == "POST":
            try:
                before = dict(fighter)
                fighter_values = fighter_form_values()
                baseline = fighter_baseline_values()
                conn.execute(
                    """
                    UPDATE fighters SET name=?, tier=?, age=?, height=?, weight=?, current_cost=?, notes=?, nickname=?, fighting_style=?, preferred_role=?, role_or_weapon=?, known_for=?, why_buhurt=?, joined_year=?, reputation=?, image_url=?, image_credit=?, image_source_url=?, bio=?, hero_quote=?
                    WHERE id=?
                    """,
                    fighter_values + (fighter_id,)
                )
                conn.execute(
                    "INSERT INTO baseline_stats(fighter_id,training,support) VALUES(?,?,?) ON CONFLICT(fighter_id) DO UPDATE SET training=excluded.training,support=excluded.support",
                    (fighter_id, baseline["training"], baseline["support"])
                )
                log_audit(conn, "fighter", fighter_id, "update", f"Updated fighter {fighter_values[0]}.", before_state=before, after_state={"id": fighter_id, "name": fighter_values[0]})
            except ValidationError as exc:
                flash(str(exc))
                baseline_row = conn.execute("SELECT * FROM baseline_stats WHERE fighter_id=?", (fighter_id,)).fetchone() or {"training": 0, "support": 0}
                return render_template(
                    "admin_fighter_form.html",
                    fighter=submitted_fighter_form(fighter),
                    baseline=submitted_baseline(baseline_row),
                    current_totals=fighter_admin_totals(conn, fighter_id),
                ), 400
            except sqlite3.IntegrityError:
                flash("A fighter with that name already exists.")
                baseline_row = conn.execute("SELECT * FROM baseline_stats WHERE fighter_id=?", (fighter_id,)).fetchone() or {"training": 0, "support": 0}
                return render_template(
                    "admin_fighter_form.html",
                    fighter=submitted_fighter_form(fighter),
                    baseline=submitted_baseline(baseline_row),
                    current_totals=fighter_admin_totals(conn, fighter_id),
                ), 400
            conn.commit()
            flash("Fighter updated.")
            return redirect(url_for("admin_fighters"))
        baseline = conn.execute("SELECT * FROM baseline_stats WHERE fighter_id=?", (fighter_id,)).fetchone() or {"training": 0, "support": 0}
        return render_template(
            "admin_fighter_form.html",
            fighter=fighter,
            baseline=baseline,
            current_totals=fighter_admin_totals(conn, fighter_id),
        )
