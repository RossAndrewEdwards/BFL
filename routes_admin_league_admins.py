def register_admin_league_admin_routes(app, deps):
    admin_required = deps["admin_required"]
    db = deps["db"]
    flash = deps["flash"]
    redirect = deps["redirect"]
    url_for = deps["url_for"]
    abort = deps["abort"]

    def redirect_to_league_workspace(user_id=None):
        conn = db()
        if user_id is not None:
            user = conn.execute(
                "SELECT id, league_id FROM users WHERE id=? AND role='league_admin'",
                (user_id,),
            ).fetchone()
            if not user:
                abort(404)
            if user["league_id"]:
                flash("League admins are now managed from the league workspace.")
                return redirect(url_for("admin_league_edit", league_id=user["league_id"]))
        flash("League admins are now managed from the league workspace.")
        return redirect(url_for("admin_leagues"))

    @app.route("/admin/league-admins")
    @admin_required
    def admin_league_admins():
        return redirect_to_league_workspace()

    @app.route("/admin/league-admins/new", methods=["GET", "POST"])
    @admin_required
    def admin_league_admin_new():
        return redirect_to_league_workspace()

    @app.route("/admin/league-admins/<int:user_id>", methods=["GET", "POST"])
    @admin_required
    def admin_league_admin_edit(user_id):
        return redirect_to_league_workspace(user_id=user_id)
