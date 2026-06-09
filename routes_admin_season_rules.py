def register_admin_season_rule_routes(app, deps):
    ValidationError = deps["ValidationError"]
    SEASON_COST_DEFAULTS = deps["SEASON_COST_DEFAULTS"]
    abort = deps["abort"]
    admin_required = deps["admin_required"]
    apply_collection_filters = deps["apply_collection_filters"]
    bool_setting = deps["bool_setting"]
    calculate_season_cost_changes = deps["calculate_season_cost_changes"]
    create_notification = deps["create_notification"]
    current_season = deps["current_season"]
    db = deps["db"]
    end_active_season = deps["end_active_season"]
    ensure_active_season = deps["ensure_active_season"]
    flash = deps["flash"]
    int_setting = deps["int_setting"]
    leaderboard_rows = deps["leaderboard_rows"]
    log_audit = deps["log_audit"]
    parse_int_field = deps["parse_int_field"]
    parse_optional_float = deps["parse_optional_float"]
    public_profile_formula_defaults = deps["public_profile_formula_defaults"]
    public_profile_formula_groups = deps["public_profile_formula_groups"]
    redirect = deps["redirect"]
    render_template = deps["render_template"]
    request = deps["request"]
    require_active_season_editable = deps["require_active_season_editable"]
    rules_dict = deps["rules_dict"]
    season_cost_settings = deps["season_cost_settings"]
    settings_dict = deps["settings_dict"]
    team_rows = deps["team_rows"]
    url_for = deps["url_for"]

    @app.route("/admin/season/settings", methods=["GET", "POST"])
    @admin_required
    def admin_season_settings():
        conn = db()
        season = current_season(conn) or ensure_active_season(conn)
        if request.method == "POST":
            requested_status = request.form.get("season_status", season["status"]).strip()
            if requested_status not in {"active", "completed"}:
                flash("Season status is invalid.")
                return redirect(url_for("admin_season_settings"))
            if requested_status == "completed" and season["status"] == "active":
                flash("Use the End Season workflow to complete and lock the season safely.")
                return redirect(url_for("admin_end_season"))
            if requested_status == "active" and season["status"] == "completed":
                conn.execute(
                    """
                    UPDATE seasons
                    SET status='active',
                        locked=0,
                        ended_at=NULL,
                        winner_team_id=NULL,
                        winner_team_name=NULL,
                        winner_player_user_id=NULL,
                        winner_player_name=NULL,
                        final_leaderboard_json=NULL,
                        completed_at=NULL
                    WHERE id=?
                    """,
                    (season["id"],),
                )
                log_audit(
                    conn,
                    "season",
                    season["id"],
                    "reopen",
                    f"Reopened {season['name']} from season settings.",
                    before_state={"status": season["status"], "locked": season["locked"]},
                    after_state={"status": "active", "locked": 0},
                    league_id=None,
                )
                create_notification(
                    conn,
                    f"{season['name']} reopened",
                    "An admin reopened the completed season from season settings.",
                    "warning",
                )
                conn.commit()
                flash(f"{season['name']} reopened. You can now edit season settings.")
                return redirect(url_for("admin_season_settings"))
            try:
                require_active_season_editable(conn, "Season settings changes")
                season_name = request.form.get("season_name", "").strip()
                if not season_name:
                    raise ValidationError("Season name is required.")
                conn.execute("UPDATE seasons SET name=? WHERE id=?", (season_name, season["id"]))
                before_settings = {
                    "season_name": season["name"],
                    "status": season["status"],
                }
                log_audit(
                    conn,
                    "season",
                    season["id"],
                    "settings_update",
                    f"Updated season settings for {season_name}.",
                    before_state=before_settings,
                    after_state={
                        "season_name": season_name,
                        "status": season["status"],
                    },
                    league_id=None,
                )
                conn.commit()
                flash("Season settings updated.")
            except ValidationError as exc:
                flash(str(exc))
            return redirect(url_for("admin_season_settings"))
        return render_template(
            "admin_season_settings.html",
            season=season,
        )

    @app.route("/admin/season/end", methods=["GET", "POST"])
    @admin_required
    def admin_end_season():
        conn = db()
        season = current_season(conn) or ensure_active_season(conn)
        locked = bool(season["locked"]) or season["status"] != "active"
        preview_teams = team_rows(conn)
        formula = season_cost_settings(conn)
        preview_changes = calculate_season_cost_changes(leaderboard_rows(conn), preview_teams, formula)
        preview_changes.sort(key=lambda row: abs(row["new_cost"] - row["old_cost"]), reverse=True)
        if request.method == "POST":
            confirmation = request.form.get("confirmation_text", "").strip().upper()
            if confirmation != "END SEASON":
                flash("Type END SEASON to confirm this action.")
                return (
                    render_template(
                        "admin_end_season.html",
                        season=season,
                        preview_teams=preview_teams,
                        preview_changes=preview_changes[:12],
                        formula=formula,
                        locked=locked,
                    ),
                    400,
                )
            try:
                result = end_active_season(conn)
            except ValidationError as exc:
                flash(str(exc))
                return redirect(url_for("admin_end_season"))
            flash(
                f"{result['season_name']} ended successfully. Winner: "
                f"{result['winner_team_name'] or 'No winner'}"
                f"{' (' + result['winner_player_name'] + ')' if result['winner_player_name'] else ''}."
            )
            return redirect(url_for("admin_dashboard"))
        return render_template(
            "admin_end_season.html",
            season=season,
            preview_teams=preview_teams,
            preview_changes=preview_changes[:12],
            formula=formula,
            locked=locked,
        )

    @app.post("/admin/season/reopen")
    @admin_required
    def admin_reopen_season():
        conn = db()
        season = current_season(conn)
        if not season:
            abort(404)
        if season["status"] == "active" and not season["locked"]:
            flash(f"{season['name']} is already open.")
            return redirect(url_for("admin_end_season"))
        conn.execute(
            """
            UPDATE seasons
            SET status='active',
                locked=0,
                ended_at=NULL,
                winner_team_id=NULL,
                winner_team_name=NULL,
                winner_player_user_id=NULL,
                winner_player_name=NULL,
                final_leaderboard_json=NULL,
                completed_at=NULL
            WHERE id=?
            """,
            (season["id"],),
        )
        log_audit(
            conn,
            "season",
            season["id"],
            "reopen",
            f"Reopened {season['name']} for further edits.",
            before_state={"status": season["status"], "locked": season["locked"]},
            after_state={"status": "active", "locked": 0},
            league_id=None,
        )
        create_notification(
            conn,
            f"{season['name']} reopened",
            "An admin reopened the completed season.",
            "warning",
        )
        conn.commit()
        flash(f"{season['name']} reopened.")
        return redirect(url_for("admin_season_settings"))

    @app.route("/admin/rules", methods=["GET", "POST"])
    @admin_required
    def admin_rules():
        conn = db()
        if request.method == "POST":
            try:
                require_active_season_editable(conn, "Scoring changes")
                before_rules = {row["key"]: row["points"] for row in conn.execute("SELECT key, points FROM rules").fetchall()}
                before_settings = settings_dict(conn).copy()
                for row in conn.execute("SELECT key FROM rules").fetchall():
                    field_name = f"rule_{row['key']}"
                    if field_name in request.form:
                        conn.execute("UPDATE rules SET points=? WHERE key=?", (parse_int_field(field_name, default=0), row["key"]))
                minimum_team_size = parse_int_field("minimum_team_size", default=5, minimum=1)
                maximum_team_size = parse_int_field("maximum_team_size", default=8, minimum=1)
                if minimum_team_size > maximum_team_size:
                    raise ValidationError("Minimum team size cannot exceed maximum team size.")
                settings_to_save = {
                    "team_budget": parse_int_field("team_budget", default=500, minimum=0),
                    "minimum_team_size": minimum_team_size,
                    "maximum_team_size": maximum_team_size,
                    "tier_1_cost": parse_int_field("tier_1_cost", default=0, minimum=0),
                    "tier_2_cost": parse_int_field("tier_2_cost", default=0, minimum=0),
                    "tier_3_cost": parse_int_field("tier_3_cost", default=0, minimum=0),
                    "season_cost_round_unit": parse_int_field("season_cost_round_unit", default=5, minimum=1),
                    "season_min_cost": parse_int_field("season_min_cost", default=25, minimum=0),
                    "season_max_cost": parse_int_field("season_max_cost", default=250, minimum=0),
                    "public_fighter_scores_visible": "1" if request.form.get("public_fighter_scores_visible") == "1" else "0",
                }
                if settings_to_save["season_min_cost"] > settings_to_save["season_max_cost"]:
                    raise ValidationError("Season minimum fighter cost cannot exceed the maximum fighter cost.")
                season_pick_rate_target = request.form.get("season_pick_rate_target", "").strip() or SEASON_COST_DEFAULTS["season_pick_rate_target"]
                season_cost_sensitivity = request.form.get("season_cost_sensitivity", "").strip() or SEASON_COST_DEFAULTS["season_cost_sensitivity"]
                season_cost_adjustment_cap = request.form.get("season_cost_adjustment_cap", "").strip() or SEASON_COST_DEFAULTS["season_cost_adjustment_cap"]
                try:
                    season_pick_rate_target_value = float(season_pick_rate_target)
                    season_cost_sensitivity_value = float(season_cost_sensitivity)
                    season_cost_adjustment_cap_value = float(season_cost_adjustment_cap)
                except ValueError as exc:
                    raise ValidationError("Season cost formula values must be numeric.") from exc
                if not 0 <= season_pick_rate_target_value <= 1:
                    raise ValidationError("Season target pick rate must be between 0 and 1.")
                if season_cost_sensitivity_value < 0:
                    raise ValidationError("Season cost sensitivity cannot be negative.")
                if not 0 <= season_cost_adjustment_cap_value <= 1:
                    raise ValidationError("Season cost adjustment cap must be between 0 and 1.")
                settings_to_save["season_pick_rate_target"] = season_pick_rate_target_value
                settings_to_save["season_cost_sensitivity"] = season_cost_sensitivity_value
                settings_to_save["season_cost_adjustment_cap"] = season_cost_adjustment_cap_value
                cost_mode = request.form.get("cost_mode", "Current Season")
                if cost_mode not in {"Current Season", "Next Season"}:
                    raise ValidationError("Cost mode is invalid.")
                settings_to_save["cost_mode"] = cost_mode
                current_rules = rules_dict(conn)
                training_points = parse_int_field("training_points", default=current_rules.get("training", 0))
                support_points = parse_int_field("support_points", default=current_rules.get("support", 0))
                existing_settings = settings_dict(conn)
                for key, default_value in public_profile_formula_defaults.items():
                    raw_value = request.form.get(key, "").strip()
                    if raw_value == "":
                        raw_value = existing_settings.get(key, default_value)
                    try:
                        numeric_value = float(raw_value)
                    except ValueError as exc:
                        raise ValidationError("Trait formula values must be numeric.") from exc
                    if numeric_value < 0:
                        raise ValidationError("Trait formula values cannot be negative.")
                    settings_to_save[key] = numeric_value
                for key, value in settings_to_save.items():
                    conn.execute(
                        "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, str(value)),
                    )
                conn.execute("UPDATE rules SET points=? WHERE key='training'", (training_points,))
                conn.execute("UPDATE rules SET points=? WHERE key='support'", (support_points,))
            except ValidationError as exc:
                flash(str(exc))
                return redirect(url_for("admin_rules"))
            after_rules = {row["key"]: row["points"] for row in conn.execute("SELECT key, points FROM rules").fetchall()}
            after_settings = settings_dict(conn).copy()
            log_audit(
                conn,
                "rules",
                None,
                "update",
                "Updated platform-wide rules and settings.",
                before_state={"rules": before_rules, "settings": before_settings},
                after_state={"rules": after_rules, "settings": after_settings},
                league_id=None,
            )
            conn.commit()
            flash("Rules and settings updated.")
            return redirect(url_for("admin_rules"))
        rules = [dict(row) for row in conn.execute("SELECT * FROM rules ORDER BY rowid").fetchall()]
        display_rules = [row for row in rules if row["key"] not in {"training", "support"}]
        display_rules, toolbar = apply_collection_filters(
            display_rules,
            search_fields=["label", "notes"],
            sort_options=[
                {"value": "default", "label": "Default Order"},
                {"value": "category", "label": "Category (A-Z)", "key": lambda row: row["label"]},
                {"value": "points", "label": "Points (High-Low)", "key": lambda row: row["points"], "reverse": True},
            ],
            search_placeholder="Search scoring categories or notes",
        )
        settings = settings_dict(conn)
        return render_template(
            "admin_rules.html",
            rules=display_rules,
            settings=settings,
            toolbar=toolbar,
            public_profile_formula_groups=public_profile_formula_groups(settings),
            training_points=rules_dict(conn).get("training", 0),
            support_points=rules_dict(conn).get("support", 0),
        )
