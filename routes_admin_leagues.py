import re
import sqlite3


def register_admin_league_routes(app, deps):
    admin_required = deps["admin_required"]
    site_admin_required = deps["site_admin_required"]
    current_user = deps["current_user"]
    is_site_admin = deps["is_site_admin"]
    db = deps["db"]
    render_template = deps["render_template"]
    request = deps["request"]
    flash = deps["flash"]
    redirect = deps["redirect"]
    url_for = deps["url_for"]
    ValidationError = deps["ValidationError"]
    abort = deps["abort"]
    log_audit = deps["log_audit"]
    ensure_active_league_membership = deps["ensure_active_league_membership"]
    effective_league_id = deps["effective_league_id"]
    generate_unique_join_code = deps["generate_unique_join_code"]

    valid_statuses = {"pending", "active", "inactive", "archived"}
    starter_templates = {
        "blank": {
            "label": "Blank league",
            "description": "Start with an empty league and configure everything manually.",
            "defaults": {},
        },
        "club_launch": {
            "label": "Club launch",
            "description": "Good default for a new club rollout with active status and starter quotas.",
            "defaults": {
                "status": "active",
                "max_players": 24,
                "max_teams": 24,
                "description": "Starter setup for a new club league on the Buhurt Fantasy League platform.",
            },
        },
        "private_pilot": {
            "label": "Private pilot",
            "description": "Smaller member cap for a soft launch or trial run.",
            "defaults": {
                "status": "pending",
                "max_players": 8,
                "max_teams": 8,
                "description": "Pilot league setup for testing a club before a wider launch.",
            },
        },
    }

    def starter_template_choices():
        return [
            {"key": key, **value}
            for key, value in starter_templates.items()
        ]

    def starter_template_key():
        key = request.form.get("starter_template", "blank").strip() or "blank"
        if key not in starter_templates:
            raise ValidationError("Choose a valid starter template.")
        return key

    def starter_template_defaults(template_key):
        return dict(starter_templates[template_key]["defaults"])

    def league_usage_rows(conn):
        return conn.execute(
            """
            SELECT
                l.*,
                COALESCE(player_counts.player_count, 0) AS player_count,
                COALESCE(team_counts.team_count, 0) AS team_count,
                COALESCE(fighter_counts.fighter_count, 0) AS fighter_count,
                COALESCE(event_counts.result_count, 0) AS result_count,
                COALESCE(admin_counts.admin_count, 0) AS admin_count
            FROM leagues l
            LEFT JOIN (
                SELECT league_id, COUNT(*) AS player_count
                FROM users
                WHERE role='player'
                GROUP BY league_id
            ) AS player_counts ON player_counts.league_id = l.id
            LEFT JOIN (
                SELECT league_id, COUNT(*) AS team_count
                FROM fantasy_teams
                GROUP BY league_id
            ) AS team_counts ON team_counts.league_id = l.id
            LEFT JOIN (
                SELECT league_id, COUNT(*) AS fighter_count
                FROM fighters
                GROUP BY league_id
            ) AS fighter_counts ON fighter_counts.league_id = l.id
            LEFT JOIN (
                SELECT league_id, COUNT(*) AS result_count
                FROM event_results
                GROUP BY league_id
            ) AS event_counts ON event_counts.league_id = l.id
            LEFT JOIN (
                SELECT league_id, COUNT(*) AS admin_count
                FROM users
                WHERE role='league_admin'
                GROUP BY league_id
            ) AS admin_counts ON admin_counts.league_id = l.id
            ORDER BY l.name, l.id
            """
        ).fetchall()

    def league_admin_rows(conn, league_id):
        return conn.execute(
            """
            SELECT id, username, display_name, league_id
            FROM users
            WHERE role='league_admin' AND league_id=?
            ORDER BY display_name, username
            """,
            (league_id,),
        ).fetchall()

    def league_player_rows(conn, league_id):
        return conn.execute(
            """
            SELECT
                u.id,
                u.username,
                u.display_name,
                COALESCE(lm.manager_limit, u.manager_limit) AS manager_limit,
                COUNT(t.id) AS team_count
            FROM league_memberships lm
            JOIN users u ON u.id = lm.user_id
            LEFT JOIN fantasy_teams t ON t.player_user_id = u.id
              AND t.league_id=lm.league_id
            WHERE lm.league_id=?
              AND lm.status='active'
              AND (lm.role='player' OR lm.manager_limit > 0)
            GROUP BY u.id, u.username, u.display_name, COALESCE(lm.manager_limit, u.manager_limit)
            ORDER BY u.display_name, u.username
            """,
            (league_id,),
        ).fetchall()

    def league_team_rows(conn, league_id):
        return conn.execute(
            """
            SELECT
                t.id,
                t.team_name,
                t.manager,
                u.display_name AS player_name
            FROM fantasy_teams t
            LEFT JOIN users u ON u.id = t.player_user_id
            WHERE t.league_id=?
            ORDER BY t.team_name, t.id
            """,
            (league_id,),
        ).fetchall()

    def league_workspace_summary(conn, league_id, user_id):
        player_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM league_memberships
            WHERE league_id=?
              AND status='active'
              AND (role='player' OR manager_limit > 0)
            """,
            (league_id,),
        ).fetchone()[0]
        team_count = conn.execute(
            "SELECT COUNT(*) FROM fantasy_teams WHERE league_id=?",
            (league_id,),
        ).fetchone()[0]
        fighter_count = conn.execute(
            "SELECT COUNT(*) FROM fighters WHERE league_id=?",
            (league_id,),
        ).fetchone()[0]
        event_count = conn.execute(
            """
            SELECT COUNT(DISTINCT COALESCE(scheduled_event_id, event_name || '|' || event_date))
            FROM event_results
            WHERE league_id=?
            """,
            (league_id,),
        ).fetchone()[0]
        latest_event = conn.execute(
            """
            SELECT event_name, event_date
            FROM event_results
            WHERE league_id=?
            ORDER BY event_date DESC, id DESC
            LIMIT 1
            """,
            (league_id,),
        ).fetchone()
        recent_notification = conn.execute(
            """
            SELECT title, created_at
            FROM notifications
            WHERE league_id=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (league_id,),
        ).fetchone()
        membership_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM league_memberships
            WHERE league_id=? AND status='active'
            """,
            (league_id,),
        ).fetchone()[0]
        return {
            "player_count": player_count,
            "team_count": team_count,
            "fighter_count": fighter_count,
            "event_count": event_count,
            "membership_count": membership_count,
            "latest_event": latest_event,
            "recent_notification": recent_notification,
            "league_admin_count": conn.execute(
                """
                SELECT COUNT(*)
                FROM league_memberships
                WHERE league_id=? AND status='active' AND role='league_admin'
                """,
                (league_id,),
            ).fetchone()[0],
            "user_team_count": conn.execute(
                "SELECT COUNT(*) FROM fantasy_teams WHERE league_id=? AND player_user_id=?",
                (league_id, user_id),
            ).fetchone()[0],
        }

    def submitted_league(existing=None):
        league = dict(existing) if existing else {}
        league["starter_template"] = request.form.get("starter_template", league.get("starter_template", "blank")).strip() or "blank"
        league["slug"] = request.form.get("slug", league.get("slug", "")).strip().lower()
        league["name"] = request.form.get("name", league.get("name", "")).strip()
        league["club_name"] = request.form.get("club_name", league.get("club_name", "")).strip()
        league["status"] = request.form.get("status", league.get("status", "pending")).strip().lower()
        league["description"] = request.form.get("description", league.get("description", "")).strip()
        league["contact_email"] = request.form.get("contact_email", league.get("contact_email", "")).strip()
        league["logo_url"] = request.form.get("logo_url", league.get("logo_url", "")).strip()
        raw_max_players = request.form.get("max_players", "")
        if raw_max_players == "":
            league["max_players"] = None
            league["max_teams"] = None
        else:
            try:
                parsed_max_players = int(raw_max_players)
            except ValueError:
                league["max_players"] = raw_max_players
                league["max_teams"] = raw_max_players
            else:
                league["max_players"] = parsed_max_players
                league["max_teams"] = parsed_max_players
        return league

    def league_form_values():
        template_key = starter_template_key()
        template_defaults = starter_template_defaults(template_key)
        slug = request.form.get("slug", "").strip().lower()
        name = request.form.get("name", "").strip()
        club_name = request.form.get("club_name", "").strip()
        status = request.form.get("status", str(template_defaults.get("status", "pending"))).strip().lower()
        description = request.form.get("description", "").strip() or template_defaults.get("description")
        contact_email = request.form.get("contact_email", "").strip() or None
        logo_url = request.form.get("logo_url", "").strip() or None
        if not slug:
            raise ValidationError("League slug is required.")
        if not re.fullmatch(r"[a-z0-9-]+", slug):
            raise ValidationError("League slug may only contain lowercase letters, numbers, and hyphens.")
        if not name:
            raise ValidationError("League name is required.")
        if not club_name:
            raise ValidationError("Club name is required.")
        if status not in valid_statuses:
            raise ValidationError("Choose a valid league status.")

        def parse_optional_int(name, label):
            raw = request.form.get(name, "").strip()
            if not raw:
                return template_defaults.get(name)
            try:
                value = int(raw)
            except ValueError as exc:
                raise ValidationError(f"{label} must be a whole number.") from exc
            if value < 0:
                raise ValidationError(f"{label} cannot be negative.")
            return value

        return {
            "starter_template": template_key,
            "slug": slug,
            "name": name,
            "club_name": club_name,
            "status": status,
            "description": description,
            "contact_email": contact_email,
            "logo_url": logo_url,
            "max_players": parse_optional_int("max_players", "Maximum players"),
            "max_teams": parse_optional_int("max_players", "Maximum players"),
        }

    def league_edit_context(conn, league, submitted_values=None):
        return {
            "league": submitted_values or league,
            "is_new": False,
            "starter_templates": starter_template_choices(),
            "league_admin_rows": league_admin_rows(conn, league["id"]),
            "league_players": league_player_rows(conn, league["id"]),
            "league_teams": league_team_rows(conn, league["id"]),
        }

    @app.route("/admin/leagues")
    @site_admin_required
    def admin_leagues():
        return render_template("admin_leagues.html", rows=league_usage_rows(db()))

    @app.route("/admin/leagues/new", methods=["GET", "POST"])
    @site_admin_required
    def admin_league_new():
        conn = db()
        if request.method == "POST":
            try:
                values = league_form_values()
                conn.execute(
                    """
                    INSERT INTO leagues(
                        slug, name, club_name, status, description, contact_email,
                        join_code,
                        logo_url, max_players, max_teams, created_at, updated_at
                    )
                    VALUES(?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
                    """,
                    (
                        values["slug"],
                        values["name"],
                        values["club_name"],
                        values["status"],
                        values["description"],
                        values["contact_email"],
                        generate_unique_join_code(conn),
                        values["logo_url"],
                        values["max_players"],
                        values["max_teams"],
                    ),
                )
                league_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                log_audit(
                    conn,
                    "league",
                    league_id,
                    "create",
                    f"Created league {values['name']}.",
                    after_state=values,
                    league_id=league_id,
                )
                conn.commit()
                flash("League created. You can now assign league admins and review league members here.")
                return redirect(url_for("admin_league_edit", league_id=league_id))
            except ValidationError as exc:
                flash(str(exc))
                return render_template(
                    "admin_league_form.html",
                    league=submitted_league(),
                    is_new=True,
                    starter_templates=starter_template_choices(),
                ), 400
            except sqlite3.IntegrityError:
                flash("That league slug is already in use.")
                return render_template(
                    "admin_league_form.html",
                    league=submitted_league(),
                    is_new=True,
                    starter_templates=starter_template_choices(),
                ), 400
        return render_template(
            "admin_league_form.html",
            league={"starter_template": "blank"},
            is_new=True,
            starter_templates=starter_template_choices(),
        )

    @app.route("/admin/leagues/<int:league_id>", methods=["GET", "POST"])
    @site_admin_required
    def admin_league_edit(league_id):
        conn = db()
        league = conn.execute("SELECT * FROM leagues WHERE id=?", (league_id,)).fetchone()
        if not league:
            abort(404)
        if request.method == "POST":
            action = request.form.get("action", "save_league")
            try:
                if action == "save_league":
                    values = league_form_values()
                    before = dict(league)
                    conn.execute(
                        """
                        UPDATE leagues
                        SET slug=?,
                            name=?,
                            club_name=?,
                            status=?,
                            description=?,
                            contact_email=?,
                            logo_url=?,
                            max_players=?,
                            max_teams=?,
                            updated_at=CURRENT_TIMESTAMP
                        WHERE id=?
                        """,
                        (
                            values["slug"],
                            values["name"],
                            values["club_name"],
                            values["status"],
                            values["description"],
                            values["contact_email"],
                            values["logo_url"],
                            values["max_players"],
                            values["max_teams"],
                            league_id,
                        ),
                    )
                    log_audit(
                        conn,
                        "league",
                        league_id,
                        "update",
                        f"Updated league {values['name']}.",
                        before_state=before,
                        after_state={**before, **values},
                        league_id=league_id,
                    )
                    success_message = "League updated."
                elif action == "remove_admin":
                    raw_user_id = request.form.get("user_id", "").strip()
                    try:
                        user_id = int(raw_user_id)
                    except ValueError as exc:
                        raise ValidationError("Choose a valid league admin.") from exc
                    admin_user = conn.execute(
                        "SELECT * FROM users WHERE id=? AND role='league_admin' AND league_id=?",
                        (user_id, league_id),
                    ).fetchone()
                    if not admin_user:
                        raise ValidationError("Choose a valid league admin.")
                    conn.execute("UPDATE users SET role='player' WHERE id=?", (user_id,))
                    ensure_active_league_membership(
                        conn,
                        user_id,
                        league_id,
                        role="player",
                        manager_limit=admin_user["manager_limit"],
                    )
                    log_audit(
                        conn,
                        "user",
                        user_id,
                        "demote",
                        f"Removed league admin access for {admin_user['display_name']}.",
                        before_state={"role": admin_user["role"], "league_id": admin_user["league_id"]},
                        after_state={"role": "player", "league_id": admin_user["league_id"]},
                        league_id=league_id,
                    )
                    success_message = "League admin access removed."
                else:
                    raise ValidationError("Choose a valid league management action.")
                conn.commit()
                flash(success_message)
                return redirect(url_for("admin_league_edit", league_id=league_id))
            except ValidationError as exc:
                flash(str(exc))
                submitted_values = submitted_league(league) if action == "save_league" else league
                return render_template("admin_league_form.html", **league_edit_context(conn, league, submitted_values=submitted_values)), 400
            except sqlite3.IntegrityError:
                if action == "save_league":
                    flash("That league slug is already in use.")
                    submitted_values = submitted_league(league)
                else:
                    flash("That username is already in use.")
                    submitted_values = league
                return render_template("admin_league_form.html", **league_edit_context(conn, league, submitted_values=submitted_values)), 400
        return render_template("admin_league_form.html", **league_edit_context(conn, league))

    @app.route("/admin/my-league", methods=["GET", "POST"])
    @admin_required
    def admin_my_league():
        user = current_user()
        if is_site_admin(user):
            return redirect(url_for("admin_leagues"))
        current_league_id = effective_league_id()
        if not user or not current_league_id:
            abort(404)
        conn = db()
        league = conn.execute("SELECT * FROM leagues WHERE id=?", (current_league_id,)).fetchone()
        if not league:
            abort(404)
        membership = conn.execute(
            """
            SELECT *
            FROM league_memberships
            WHERE user_id=? AND league_id=? AND status='active'
            LIMIT 1
            """,
            (user["id"], league["id"]),
        ).fetchone()
        if not membership:
            abort(404)
        quota = {
            "max_players": league["max_players"],
            "max_teams": league["max_teams"],
            "players_used": conn.execute(
                """
                SELECT COUNT(*)
                FROM league_memberships
                WHERE league_id=? AND status='active' AND (role='player' OR manager_limit > 0)
                """,
                (league["id"],),
            ).fetchone()[0],
            "teams_used": conn.execute(
                "SELECT COUNT(*) FROM fantasy_teams WHERE league_id=?",
                (league["id"],),
            ).fetchone()[0],
        }
        quota["players_remaining"] = None if quota["max_players"] is None else max(0, int(quota["max_players"]) - int(quota["players_used"]))
        quota["teams_remaining"] = None if quota["max_teams"] is None else max(0, int(quota["max_teams"]) - int(quota["teams_used"]))
        workspace = league_workspace_summary(conn, league["id"], user["id"])
        if request.method == "POST":
            action = request.form.get("action", "save_branding")
            if action == "save_branding":
                logo_url = request.form.get("logo_url", "").strip() or None
                before = dict(league)
                conn.execute(
                    "UPDATE leagues SET logo_url=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (logo_url, league["id"]),
                )
                log_audit(
                    conn,
                    "league",
                    league["id"],
                    "update_branding",
                    f"Updated league branding for {league['name']}.",
                    before_state={"logo_url": before.get("logo_url")},
                    after_state={"logo_url": logo_url},
                    league_id=league["id"],
                )
                flash("League branding updated.")
            elif action == "regenerate_join_code":
                before = dict(league)
                join_code = generate_unique_join_code(conn)
                conn.execute(
                    "UPDATE leagues SET join_code=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (join_code, league["id"]),
                )
                log_audit(
                    conn,
                    "league",
                    league["id"],
                    "regenerate_join_code",
                    f"Regenerated join code for {league['name']}.",
                    before_state={"join_code": before.get("join_code")},
                    after_state={"join_code": join_code},
                    league_id=league["id"],
                )
                flash("League join code regenerated.")
            elif action == "enable_self_participation":
                ensure_active_league_membership(
                    conn,
                    user["id"],
                    league["id"],
                    role="league_admin",
                    manager_limit=max(1, int(membership["manager_limit"] or 0)),
                )
                log_audit(
                    conn,
                    "league_membership",
                    membership["id"],
                    "enable_participation",
                    f"Enabled league-admin participation for {user['display_name']} in {league['name']}.",
                    before_state={"manager_limit": membership["manager_limit"]},
                    after_state={"manager_limit": max(1, int(membership["manager_limit"] or 0))},
                    league_id=league["id"],
                )
                flash("You can now participate as a player in this league.")
            else:
                flash("Choose a valid league action.")
                return redirect(url_for("admin_my_league"))
            conn.commit()
            return redirect(url_for("admin_my_league"))
        return render_template("admin_my_league.html", league=league, membership=membership, quota=quota, workspace=workspace)
