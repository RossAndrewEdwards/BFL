import json


def register_admin_ops_routes(app, deps):
    abort = deps["abort"]
    admin_required = deps["admin_required"]
    apply_collection_filters = deps["apply_collection_filters"]
    audit_rows = deps["audit_rows"]
    create_notification = deps["create_notification"]
    db = deps["db"]
    effective_league_id = deps["effective_league_id"]
    flash = deps["flash"]
    json_module = deps["json"]
    log_audit = deps["log_audit"]
    redirect = deps["redirect"]
    render_template = deps["render_template"]
    request = deps["request"]
    url_for = deps["url_for"]
    get_ops_engine = deps.get("get_ops_engine")
    ValidationError = deps.get("ValidationError") or Exception

    @app.route("/admin/notifications", methods=["GET", "POST"])
    @admin_required
    def admin_notifications():
        conn = db()
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            body = request.form.get("body", "").strip()
            kind = request.form.get("kind", "update").strip() or "update"
            expires_at = request.form.get("expires_at", "").strip() or None
            if not title or not body:
                flash("Title and body are required.")
                return redirect(url_for("admin_notifications"))
            if get_ops_engine:
                ops_engine = get_ops_engine(conn)
                ops_engine.alerts.publish(title, body, kind, expires_at, league_id=None)
            else:
                conn.execute(
                    """
                    INSERT INTO notifications(league_id,title,body,kind,created_at,expires_at,is_active)
                    VALUES(NULL,?,?,?,CURRENT_TIMESTAMP,?,1)
                    """,
                    (title, body, kind, expires_at),
                )
                log_audit(conn, "notification", None, "create", f"Notification created: {title}", league_id=None)
            conn.commit()
            flash("Notification published.")
            return redirect(url_for("admin_notifications"))
        rows = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM notifications WHERE league_id IS NULL ORDER BY id DESC"
            ).fetchall()
        ]
        for row in rows:
            row["status_label"] = "Active" if row["is_active"] else "Paused"
        rows, toolbar = apply_collection_filters(
            rows,
            search_fields=["title", "body", "kind", "status_label"],
            filters=[
                {"name": "kind", "label": "Kind", "field": "kind"},
                {"name": "status", "label": "Status", "field": "status_label"},
            ],
            sort_options=[
                {"value": "default", "label": "Newest First"},
                {"value": "oldest", "label": "Oldest First", "key": lambda row: row["id"]},
                {"value": "title", "label": "Title (A-Z)", "key": lambda row: row["title"]},
            ],
            search_placeholder="Search titles, body text, kind, or status",
        )
        return render_template("admin_notifications.html", rows=rows, toolbar=toolbar)

    @app.post("/admin/notifications/<int:notification_id>/toggle")
    @admin_required
    def admin_notification_toggle(notification_id):
        conn = db()
        row = conn.execute(
            "SELECT * FROM notifications WHERE id=? AND league_id IS NULL",
            (notification_id,),
        ).fetchone()
        if not row:
            abort(404)
        if get_ops_engine:
            ops_engine = get_ops_engine(conn)
            ops_engine.alerts.toggle(notification_id)
        else:
            new_value = 0 if row["is_active"] else 1
            conn.execute("UPDATE notifications SET is_active=? WHERE id=?", (new_value, notification_id))
            log_audit(conn, "notification", notification_id, "toggle", f"Notification {'activated' if new_value else 'paused'}: {row['title']}", league_id=None)
        conn.commit()
        flash("Notification updated.")
        return redirect(url_for("admin_notifications"))

    @app.route("/admin/media", methods=["GET", "POST"])
    @admin_required
    def admin_media():
        conn = db()
        if request.method == "POST":
            event_name = request.form.get("event_name", "").strip()
            event_date = request.form.get("event_date", "").strip()
            if not event_name or not event_date:
                flash("Event name and date are required.")
                return redirect(url_for("admin_media"))
            conn.execute(
                """
                INSERT INTO event_banners(event_name,event_date,headline,subheading,image_url)
                VALUES(?,?,?,?,?)
                ON CONFLICT(event_name,event_date) DO UPDATE SET
                    headline=excluded.headline,
                    subheading=excluded.subheading,
                    image_url=excluded.image_url
                """,
                (
                    event_name,
                    event_date,
                    request.form.get("headline", "").strip(),
                    request.form.get("subheading", "").strip(),
                    request.form.get("image_url", "").strip(),
                ),
            )
            log_audit(conn, "event_banner", None, "upsert", f"Updated media for {event_name} ({event_date}).", league_id=None)
            conn.commit()
            flash("Event media saved.")
            return redirect(url_for("admin_media"))
        banners = [dict(row) for row in conn.execute("SELECT * FROM event_banners ORDER BY event_date DESC, event_name").fetchall()]
        fighters = [dict(row) for row in conn.execute("SELECT id, name, image_url, image_credit, image_source_url, hero_quote, bio FROM fighters ORDER BY name").fetchall()]
        for row in banners:
            row["season"] = row["event_date"][:4]
        for row in fighters:
            row["bio_status"] = "Added" if row["bio"] else "Missing"
            row["image_status"] = "Added" if row["image_url"] else "Missing"
        banners, banner_toolbar = apply_collection_filters(
            banners,
            search_fields=["event_name", "event_date", "headline", "image_url", "season"],
            filters=[
                {"name": "season", "label": "Season", "field": "season"},
            ],
            sort_options=[
                {"value": "default", "label": "Latest Event"},
                {"value": "event", "label": "Event Name (A-Z)", "key": lambda row: row["event_name"]},
            ],
            search_placeholder="Search events, headlines, dates, or seasons",
            param_prefix="banner_",
        )
        fighters, fighter_toolbar = apply_collection_filters(
            fighters,
            search_fields=["name", "image_url", "image_credit", "image_source_url", "hero_quote", "bio"],
            filters=[
                {"name": "image_status", "label": "Image", "field": "image_status"},
                {"name": "bio_status", "label": "Bio", "field": "bio_status"},
            ],
            sort_options=[
                {"value": "default", "label": "Name (A-Z)"},
                {"value": "image", "label": "Image Status", "key": lambda row: row["image_status"]},
            ],
            search_placeholder="Search fighters, credits, quotes, or source URLs",
            param_prefix="fighter_",
        )
        return render_template(
            "admin_media.html",
            banners=banners,
            fighters=fighters,
            banner_toolbar=banner_toolbar,
            fighter_toolbar=fighter_toolbar,
        )

    @app.route("/admin/audit")
    @admin_required
    def admin_audit():
        rows = [dict(row) for row in audit_rows(db())]
        for row in rows:
            row["league_name_display"] = row.get("league_name") or "Platform"
            row["before_preview"] = json_module.dumps(json_module.loads(row["before_state"]), indent=2, sort_keys=True) if row.get("before_state") else ""
            row["after_preview"] = json_module.dumps(json_module.loads(row["after_state"]), indent=2, sort_keys=True) if row.get("after_state") else ""
        rows, toolbar = apply_collection_filters(
            rows,
            search_fields=["actor_name", "entity_type", "action", "message", "created_at", "before_preview", "after_preview", "league_name_display"],
            filters=[
                {"name": "league", "label": "League", "field": "league_name_display"},
                {"name": "entity", "label": "Entity", "field": "entity_type"},
                {"name": "action", "label": "Action", "field": "action"},
            ],
            sort_options=[
                {"value": "default", "label": "Newest First"},
                {"value": "oldest", "label": "Oldest First", "key": lambda row: row["id"]},
            ],
            search_placeholder="Search actors, entities, actions, or messages",
        )
        return render_template("admin_audit.html", rows=rows, toolbar=toolbar)

    @app.post("/admin/audit/<int:audit_id>/rollback")
    @admin_required
    def admin_audit_rollback(audit_id):
        conn = db()
        if get_ops_engine:
            try:
                ops_engine = get_ops_engine(conn)
                ops_engine.journal.rollback(audit_id)
                conn.commit()
                flash("Rollback applied.")
            except ValidationError as exc:
                conn.rollback()
                flash(str(exc))
        else:
            row = conn.execute("SELECT * FROM audit_logs WHERE id=?", (audit_id,)).fetchone()
            if not row:
                abort(404)
            if not row["rollback_type"]:
                flash("That audit entry cannot be rolled back.")
                return redirect(url_for("admin_audit"))
            before_state = json.loads(row["before_state"]) if row["before_state"] else None
            after_state = json.loads(row["after_state"]) if row["after_state"] else None
            rollback_type = row["rollback_type"]
            if rollback_type == "event_create":
                conn.execute("DELETE FROM event_results WHERE id=?", (row["entity_id"],))
            elif rollback_type == "attendance_create":
                conn.execute("DELETE FROM attendance_scores WHERE id=?", (row["entity_id"],))
            elif rollback_type == "event_delete" and before_state:
                conn.execute(
                    """
                    INSERT INTO event_results(id,scheduled_event_id,event_date,event_name,fighter_id,league_id,rounds_fought,special_awards,gold_medals,silver_medals,bronze_medals,kills,assists,deaths,sit_downs,yellow_cards,red_cards)
                    VALUES(:id,:scheduled_event_id,:event_date,:event_name,:fighter_id,:league_id,:rounds_fought,:special_awards,:gold_medals,:silver_medals,:bronze_medals,:kills,:assists,:deaths,:sit_downs,:yellow_cards,:red_cards)
                    """,
                    {**before_state, "league_id": before_state.get("league_id", effective_league_id(conn))},
                )
            elif rollback_type == "team_update" and before_state:
                conn.execute(
                    "UPDATE fantasy_teams SET team_name=?, manager=?, player_user_id=? WHERE id=?",
                    (
                        before_state["team"]["team_name"],
                        before_state["team"]["manager"],
                        before_state["team"].get("player_user_id"),
                        before_state["team"]["id"],
                    ),
                )
                conn.execute("DELETE FROM fantasy_team_fighters WHERE team_id=?", (before_state["team"]["id"],))
                for fighter in before_state["fighters"]:
                    conn.execute(
                        "INSERT INTO fantasy_team_fighters(team_id,fighter_id,slot) VALUES(?,?,?)",
                        (before_state["team"]["id"], fighter["fighter_id"], fighter["slot"]),
                    )
            else:
                flash("Rollback is not available for that entry.")
                return redirect(url_for("admin_audit"))
            log_audit(conn, row["entity_type"], row["entity_id"], "rollback", f"Rolled back audit entry #{audit_id}.", before_state=after_state, after_state=before_state, league_id=row["league_id"])
            conn.commit()
            flash("Rollback applied.")
        return redirect(url_for("admin_audit"))
