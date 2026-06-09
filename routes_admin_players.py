import sqlite3


def register_admin_player_routes(app, deps):
    admin_required = deps["admin_required"]
    db = deps["db"]
    now_iso = deps["now_iso"]
    player_rows = deps["player_rows"]
    apply_collection_filters = deps["apply_collection_filters"]
    render_template = deps["render_template"]
    request = deps["request"]
    player_form_values = deps["player_form_values"]
    generate_password_hash = deps["generate_password_hash"]
    effective_league_id = deps["effective_league_id"]
    create_claim_token = deps["create_claim_token"]
    log_audit = deps["log_audit"]
    ValidationError = deps["ValidationError"]
    flash = deps["flash"]
    redirect = deps["redirect"]
    url_for = deps["url_for"]
    submitted_player_form = deps["submitted_player_form"]
    abort = deps["abort"]
    teams_for_player = deps["teams_for_player"]
    active_claim_token_for_user = deps["active_claim_token_for_user"]
    create_notification = deps["create_notification"]
    scoped_league_id = deps["scoped_league_id"]
    league_quota_summary = deps["league_quota_summary"]
    require_player_capacity = deps["require_player_capacity"]
    ensure_active_league_membership = deps["ensure_active_league_membership"]
    is_site_admin = deps["is_site_admin"]
    current_user = deps["current_user"]
    site_admin_required = deps["site_admin_required"]

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

    def selected_creation_league(conn):
        user = current_user()
        if not is_site_admin(user):
            return None
        league_id = selected_scope_league_id(conn)
        if league_id is None:
            raise ValidationError("Choose a league before creating a player.")
        return conn.execute("SELECT id, name FROM leagues WHERE id=?", (league_id,)).fetchone()

    def managed_league(conn):
        league_id = selected_scope_league_id(conn)
        if league_id is None:
            raise ValidationError("Choose a valid league.")
        league = conn.execute("SELECT id, name FROM leagues WHERE id=?", (league_id,)).fetchone()
        if not league:
            raise ValidationError("Choose a valid league.")
        return league

    def scoped_player(conn, user_id):
        league_id = scoped_league_id(conn)
        if league_id is None:
            return conn.execute(
                "SELECT * FROM users WHERE id=? AND role='player'",
                (user_id,),
            ).fetchone()
        return conn.execute(
            """
            SELECT
                u.*,
                COALESCE(lm.manager_limit, u.manager_limit) AS manager_limit,
                lm.id AS membership_id,
                lm.league_id AS membership_league_id,
                lm.role AS membership_role
            FROM users u
            JOIN league_memberships lm
              ON lm.user_id = u.id
             AND lm.league_id = ?
             AND lm.status = 'active'
            WHERE u.id=?
              AND (lm.role='player' OR lm.manager_limit > 0)
            LIMIT 1
            """,
            (league_id, user_id),
        ).fetchone()

    @app.route("/admin/players")
    @admin_required
    def admin_players():
        conn = db()
        quota = None
        current_league_id = scoped_league_id(conn)
        selected_league = selected_scope_league(conn)
        if current_league_id is not None:
            quota = league_quota_summary(conn, current_league_id)
        elif selected_league is not None:
            quota = league_quota_summary(conn, selected_league["id"])
        tokens = {
            row["user_id"]: row
            for row in conn.execute(
                """
                SELECT *
                FROM claim_tokens
                WHERE used_at IS NULL AND expires_at >= ?
                ORDER BY id DESC
                """,
                (now_iso(),),
            ).fetchall()
        }
        rows = [dict(row) for row in player_rows(conn)]
        if selected_league:
            rows = [row for row in rows if row.get("league_id") == selected_league["id"]]
        for row in rows:
            invite = tokens.get(row["id"])
            if row.get("claimed_at"):
                row["claim_status"] = "Claimed"
            elif invite:
                row["claim_status"] = "Invited"
            else:
                row["claim_status"] = "Pending"
        rows, toolbar = apply_collection_filters(
            rows,
            search_fields=["display_name", "username", "team_names", "claim_status"],
            filters=[
                {"name": "claim", "label": "Claim Status", "field": "claim_status"},
            ],
            sort_options=[
                {"value": "default", "label": "Display Name"},
                {"value": "username", "label": "Username (A-Z)", "key": lambda row: row["username"]},
                {"value": "teams", "label": "Most Teams", "key": lambda row: row["managed_team_count"], "reverse": True},
            ],
            search_placeholder="Search players, usernames, linked teams, or claim status",
        )
        return render_template(
            "admin_players.html",
            rows=rows,
            tokens=tokens,
            toolbar=toolbar,
            quota=quota,
            selected_scope_league=selected_league,
            can_create_players=is_site_admin(current_user()),
            can_generate_invites=is_site_admin(current_user()),
            can_edit_players=is_site_admin(current_user()),
            can_delete_players=is_site_admin(current_user()),
        )

    @app.route("/admin/players/new", methods=["GET", "POST"])
    @site_admin_required
    def admin_player_new():
        conn = db()
        try:
            target_league = selected_creation_league(conn)
        except ValidationError as exc:
            flash(str(exc))
            return redirect(url_for("admin_leagues"))
        if request.method == "POST":
            try:
                require_player_capacity(conn, target_league["id"])
                values = player_form_values(conn, require_password=True)
                conn.execute(
                    "INSERT INTO users(username,display_name,password_hash,role,manager_limit,league_id) VALUES(?,?,?,?,?,?)",
                    (
                        values["username"],
                        values["display_name"],
                        generate_password_hash(values["password"]),
                        "player",
                        values["manager_limit"],
                        target_league["id"],
                    )
                )
                user_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
                ensure_active_league_membership(
                    conn,
                    user_id,
                    target_league["id"],
                    role="player",
                    manager_limit=values["manager_limit"],
                )
                invite = create_claim_token(conn, user_id)
                log_audit(
                    conn,
                    "user",
                    user_id,
                    "create",
                    f"Created player {values['display_name']} and generated claim invite.",
                    after_state={"display_name": values["display_name"], "username": values["username"], "league_id": target_league["id"]},
                    league_id=target_league["id"],
                )
            except ValidationError as exc:
                flash(str(exc))
                return render_template("admin_player_form.html", player=submitted_player_form(), is_new=True, managed_teams=[], invite=None), 400
            except sqlite3.IntegrityError:
                flash("That username is already in use.")
                return render_template("admin_player_form.html", player=submitted_player_form(), is_new=True, managed_teams=[], invite=None), 400
            conn.commit()
            flash(f"Player added. Claim code: {invite['code']}")
            return redirect(url_for("admin_players", league_id=target_league["id"]))
        return render_template("admin_player_form.html", player=None, is_new=True, managed_teams=[], invite=None)

    @app.route("/admin/players/<int:user_id>", methods=["GET", "POST"])
    @site_admin_required
    def admin_player_edit(user_id):
        conn = db()
        player = scoped_player(conn, user_id)
        if not player:
            abort(404)
        if request.method == "POST":
            try:
                before = dict(player)
                values = player_form_values(conn, require_password=False)
                conn.execute(
                    "UPDATE users SET username=?, display_name=?, manager_limit=? WHERE id=?",
                    (values["username"], values["display_name"], values["manager_limit"], user_id)
                )
                target_league_id = player["membership_league_id"] if "membership_league_id" in player.keys() and player["membership_league_id"] else player["league_id"]
                if target_league_id:
                    current_role = player["membership_role"] if "membership_role" in player.keys() and player["membership_role"] else "player"
                    ensure_active_league_membership(
                        conn,
                        user_id,
                        target_league_id,
                        role=current_role,
                        manager_limit=values["manager_limit"],
                    )
                if values["password"]:
                    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(values["password"]), user_id))
                log_audit(conn, "user", user_id, "update", f"Updated player {values['display_name']}.", before_state=before, after_state=values)
            except ValidationError as exc:
                flash(str(exc))
                selected_player = submitted_player_form(player)
                return render_template("admin_player_form.html", player=selected_player, is_new=False, managed_teams=teams_for_player(conn, user_id), invite=active_claim_token_for_user(conn, user_id)), 400
            except sqlite3.IntegrityError:
                flash("That username is already in use.")
                selected_player = submitted_player_form(player)
                return render_template("admin_player_form.html", player=selected_player, is_new=False, managed_teams=teams_for_player(conn, user_id), invite=active_claim_token_for_user(conn, user_id)), 400
            conn.commit()
            flash("Player updated.")
            return redirect(url_for("admin_players"))
        invite = active_claim_token_for_user(conn, user_id)
        return render_template("admin_player_form.html", player=player, is_new=False, managed_teams=teams_for_player(conn, user_id), invite=invite)

    @app.post("/admin/players/<int:user_id>/delete")
    @site_admin_required
    def admin_player_delete(user_id):
        conn = db()
        player = scoped_player(conn, user_id)
        if not player:
            abort(404)
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        log_audit(conn, "user", user_id, "delete", f"Deleted player {player['display_name']}.", before_state=dict(player))
        conn.commit()
        flash("Player deleted.")
        return redirect(url_for("admin_players"))

    @app.post("/admin/players/<int:user_id>/invite")
    @site_admin_required
    def admin_player_invite(user_id):
        conn = db()
        player = scoped_player(conn, user_id)
        if not player:
            abort(404)
        invite = create_claim_token(conn, user_id)
        log_audit(conn, "user", user_id, "invite", f"Generated claim invite for {player['display_name']}.")
        create_notification(conn, "New manager invite issued", f"Invite link created for {player['display_name']}.", "update")
        conn.commit()
        flash(f"Claim link ready. Code: {invite['code']}")
        target_league_id = player["membership_league_id"] if "membership_league_id" in player.keys() and player["membership_league_id"] else player["league_id"]
        if target_league_id:
            return redirect(url_for("admin_players", league_id=target_league_id))
        return redirect(url_for("admin_players"))

    @app.post("/admin/players/<int:user_id>/remove")
    @admin_required
    def admin_player_remove_from_league(user_id):
        conn = db()
        target_league = managed_league(conn)
        player = conn.execute(
            """
            SELECT
                u.*,
                lm.id AS membership_id,
                lm.role AS membership_role,
                lm.manager_limit AS membership_manager_limit
            FROM users u
            JOIN league_memberships lm
              ON lm.user_id = u.id
             AND lm.league_id = ?
             AND lm.status = 'active'
            WHERE u.id=?
              AND lm.role='player'
            LIMIT 1
            """,
            (target_league["id"], user_id),
        ).fetchone()
        if not player:
            abort(404)
        team_count = conn.execute(
            "SELECT COUNT(*) FROM fantasy_teams WHERE league_id=? AND player_user_id=?",
            (target_league["id"], user_id),
        ).fetchone()[0]
        if team_count:
            flash("Remove or reassign this player's teams before removing them from the league.")
            return redirect(url_for("admin_players", league_id=target_league["id"]))
        before_state = {
            "league_id": target_league["id"],
            "membership_role": player["membership_role"],
            "manager_limit": player["membership_manager_limit"],
        }
        conn.execute(
            """
            UPDATE league_memberships
            SET status='inactive',
                left_at=CURRENT_TIMESTAMP,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (player["membership_id"],),
        )
        next_membership = conn.execute(
            """
            SELECT league_id, role
            FROM league_memberships
            WHERE user_id=? AND status='active'
            ORDER BY
                CASE role
                    WHEN 'league_admin' THEN 0
                    ELSE 1
                END,
                league_id,
                id
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        conn.execute(
            "UPDATE users SET league_id=?, role=? WHERE id=?",
            (
                next_membership["league_id"] if next_membership else None,
                next_membership["role"] if next_membership else "player",
                user_id,
            ),
        )
        log_audit(
            conn,
            "user",
            user_id,
            "remove_membership",
            f"Removed {player['display_name']} from {target_league['name']}.",
            before_state=before_state,
            after_state={"league_id": target_league["id"], "status": "inactive"},
            league_id=target_league["id"],
        )
        conn.commit()
        flash("Player removed from league.")
        return redirect(url_for("admin_players", league_id=target_league["id"]))

    @app.post("/admin/players/<int:user_id>/promote-admin")
    @site_admin_required
    def admin_player_promote_admin(user_id):
        conn = db()
        target_league = selected_scope_league(conn)
        if not target_league:
            flash("Choose a league-scoped player view before promoting a league admin.")
            return redirect(url_for("admin_players"))
        player = conn.execute(
            """
            SELECT
                u.*,
                lm.role AS membership_role,
                lm.manager_limit AS membership_manager_limit
            FROM users u
            JOIN league_memberships lm
              ON lm.user_id = u.id
             AND lm.league_id = ?
             AND lm.status = 'active'
            WHERE u.id=?
              AND lm.role='player'
            LIMIT 1
            """,
            (target_league["id"], user_id),
        ).fetchone()
        if not player:
            abort(404)
        conn.execute(
            "UPDATE users SET role='league_admin', league_id=? WHERE id=?",
            (target_league["id"], user_id),
        )
        ensure_active_league_membership(
            conn,
            user_id,
            target_league["id"],
            role="league_admin",
            manager_limit=player["membership_manager_limit"] if player["membership_manager_limit"] is not None else player["manager_limit"],
        )
        log_audit(
            conn,
            "user",
            user_id,
            "promote",
            f"Promoted {player['display_name']} to league admin from league players.",
            before_state={"role": player["role"], "league_id": player["league_id"]},
            after_state={"role": "league_admin", "league_id": target_league["id"]},
            league_id=target_league["id"],
        )
        conn.commit()
        flash("League admin assigned.")
        return redirect(url_for("admin_players", league_id=target_league["id"]))
