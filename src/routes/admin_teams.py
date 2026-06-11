from src.support import team as team_support
from src.exceptions import ValidationError


def register_admin_team_routes(app, deps):
    admin_required = deps["admin_required"]
    db = deps["db"]
    apply_collection_filters = deps["apply_collection_filters"]
    filter_option_rows = deps["filter_option_rows"]
    render_template = deps["render_template"]
    request = deps["request"]
    flash = deps["flash"]
    redirect = deps["redirect"]
    url_for = deps["url_for"]
    parse_int_field_from_value = deps["parse_int_field_from_value"]
    abort = deps["abort"]
    team_rows = deps["team_rows"]
    scoped_league_id = deps["scoped_league_id"]
    league_quota_summary = deps["league_quota_summary"]
    is_site_admin = deps["is_site_admin"]
    current_user = deps["current_user"]

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

    @app.route("/admin/teams")
    @admin_required
    def admin_teams():
        conn = db()
        rows = team_rows(conn)
        quota = None
        current_league_id = scoped_league_id(conn)
        selected_league = selected_scope_league(conn)
        if current_league_id is not None:
            quota = league_quota_summary(conn, current_league_id)
        elif selected_league is not None:
            quota = league_quota_summary(conn, selected_league["id"])
        if selected_league:
            rows = [row for row in rows if row.get("league_id") == selected_league["id"]]
        rows, toolbar = apply_collection_filters(
            rows,
            search_fields=[
                "team_name",
                "player_name",
                "manager",
                "status",
                lambda row: [fighter["name"] for fighter in row["fighters"]],
            ],
            filters=[
                {"name": "status", "label": "Status", "field": "status"},
                {
                    "name": "player",
                    "label": "Player",
                    "field": "player_name",
                    "options": lambda data: filter_option_rows([row for row in data if row.get("player_name")], "player_name"),
                },
            ],
            sort_options=[
                {"value": "default", "label": "Rank"},
                {"value": "team", "label": "Team Name (A-Z)", "key": lambda row: row["team_name"]},
                {"value": "points", "label": "Points (High-Low)", "key": lambda row: row["points"], "reverse": True},
                {"value": "cost", "label": "Cost (High-Low)", "key": lambda row: row["cost"], "reverse": True},
            ],
            search_placeholder="Search teams, players, managers, or fighters",
        )
        return render_template("admin_teams.html", rows=rows, toolbar=toolbar, quota=quota, selected_scope_league=selected_league)

    @app.route("/admin/teams/new", methods=["GET", "POST"])
    @admin_required
    def admin_team_new():
        conn = db()
        if request.method == "POST":
            try:
                team_id = team_support.save_team(conn)
            except ValidationError as exc:
                flash(str(exc))
                selected = [parse_int_field_from_value("fighter_ids", raw.strip(), minimum=1) for raw in request.form.getlist("fighter_ids") if raw.strip().isdigit()]
                context = team_support.team_builder_context(conn)
                return render_template(
                    "admin_team_form.html",
                    team={
                        "team_name": request.form.get("team_name", "").strip(),
                        "manager": request.form.get("manager", "").strip(),
                        "player_user_id": request.form.get("player_user_id", type=int) if request.form.get("player_user_id") else None,
                        "image_credit": request.form.get("image_credit", "").strip(),
                        "image_source_url": request.form.get("image_source_url", "").strip(),
                    },
                    selected=selected,
                    **context,
                ), 400
            flash("Team added.")
            return redirect(url_for("admin_team_edit", team_id=team_id))
        context = team_support.team_builder_context(conn)
        return render_template("admin_team_form.html", team=None, selected=[], **context)

    @app.route("/admin/teams/<int:team_id>", methods=["GET", "POST"])
    @admin_required
    def admin_team_edit(team_id):
        conn = db()
        league_id = scoped_league_id(conn)
        team = conn.execute(
            "SELECT * FROM fantasy_teams WHERE id=? AND (? IS NULL OR league_id=?)",
            (team_id, league_id, league_id),
        ).fetchone()
        if not team:
            abort(404)
        if request.method == "POST":
            try:
                team_support.save_team(conn, team_id)
            except ValidationError as exc:
                flash(str(exc))
                selected = [parse_int_field_from_value("fighter_ids", raw.strip(), minimum=1) for raw in request.form.getlist("fighter_ids") if raw.strip().isdigit()]
                fallback_team = {
                    "id": team_id,
                    "team_name": request.form.get("team_name", "").strip(),
                    "manager": request.form.get("manager", "").strip(),
                    "player_user_id": request.form.get("player_user_id", type=int) if request.form.get("player_user_id") else None,
                    "image_credit": request.form.get("image_credit", "").strip(),
                    "image_source_url": request.form.get("image_source_url", "").strip(),
                }
                context = team_support.team_builder_context(conn)
                return render_template("admin_team_form.html", team=fallback_team, selected=selected, **context), 400
            flash("Team updated.")
            return redirect(url_for("admin_teams"))
        selected = [r["fighter_id"] for r in conn.execute("SELECT fighter_id FROM fantasy_team_fighters WHERE team_id=? ORDER BY slot", (team_id,)).fetchall()]
        context = team_support.team_builder_context(conn)
        return render_template("admin_team_form.html", team=team, selected=selected, **context)

    @app.post("/admin/teams/<int:team_id>/delete")
    @admin_required
    def admin_team_delete(team_id):
        conn = db()
        league_id = scoped_league_id(conn)
        team = conn.execute(
            "SELECT id FROM fantasy_teams WHERE id=? AND (? IS NULL OR league_id=?)",
            (team_id, league_id, league_id),
        ).fetchone()
        if not team:
            abort(404)
        try:
            before = team_support.delete_team(conn, team_id)
        except ValidationError as exc:
            flash(str(exc))
            return redirect(url_for("admin_teams"))
        if not before:
            abort(404)
        flash(f"Team {before['team']['team_name']} deleted.")
        return redirect(url_for("admin_teams"))
