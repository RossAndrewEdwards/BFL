import json


def register_player_routes(app, deps):
    from src.support.fighter_request import FighterRequestEngine
    ValidationError = deps["ValidationError"]
    admin_home_endpoint = deps["admin_home_endpoint"]
    admin_team_new_endpoint = deps["admin_team_new_endpoint"]
    admin_dashboard_endpoint = deps["admin_dashboard_endpoint"]
    check_password_hash = deps["check_password_hash"]
    apply_collection_filters = deps["apply_collection_filters"]
    can_manage_teams_in_active_league = deps["can_manage_teams_in_active_league"]
    create_notification = deps["create_notification"]
    csrf_token = deps["csrf_token"]
    current_user = deps["current_user"]
    db = deps["db"]
    ensure_active_league_membership = deps["ensure_active_league_membership"]
    flash = deps["flash"]
    generate_password_hash = deps["generate_password_hash"]
    home_payload = deps["home_payload"]
    is_admin_user = deps["is_admin_user"]
    is_site_admin = deps["is_site_admin"]
    log_audit = deps["log_audit"]
    login_required = deps["login_required"]
    now_iso = deps["now_iso"]
    parse_int_field_from_value = deps["parse_int_field_from_value"]
    player_manager_slot_usage = deps["player_manager_slot_usage"]
    redirect = deps["redirect"]
    render_template = deps["render_template"]
    request = deps["request"]
    require_player_capacity = deps["require_player_capacity"]
    save_team = deps["save_team"]
    session = deps["session"]
    team_builder_context = deps["team_builder_context"]
    team_detail_endpoint = deps["team_detail_endpoint"]
    team_rows = deps["team_rows"]
    teams_endpoint = deps["teams_endpoint"]
    teams_for_player = deps["teams_for_player"]
    url_for = deps["url_for"]
    league_for_user = deps["league_for_user"]
    abort = deps["abort"]
    get_ops_engine = deps.get("get_ops_engine")

    request_field_keys = [
        "name",
        "nickname",
        "age",
        "height",
        "weight",
        "fighting_style",
        "preferred_role",
        "role_or_weapon",
        "known_for",
        "why_buhurt",
        "joined_year",
        "bio",
        "notes",
    ]

    def eligible_memberships(conn, user_id):
        return conn.execute(
            """
            SELECT lm.*, l.name AS league_name, l.status AS league_status
            FROM league_memberships lm
            JOIN leagues l ON l.id = lm.league_id
            WHERE lm.user_id=?
              AND lm.status='active'
              AND l.status='active'
            ORDER BY
                CASE lm.role
                    WHEN 'league_admin' THEN 0
                    ELSE 1
                END,
                l.name,
                lm.id
            """,
            (user_id,),
        ).fetchall()

    def post_login_redirect(user):
        if is_site_admin(user):
            return redirect(url_for(admin_dashboard_endpoint))
        if is_admin_user(user):
            return redirect(url_for(admin_home_endpoint))
        return redirect(url_for("player_dashboard"))

    def active_membership(conn, user_id, league_id):
        return conn.execute(
            """
            SELECT *
            FROM league_memberships
            WHERE user_id=? AND league_id=? AND status='active'
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id, league_id),
        ).fetchone()

    def fighter_request_payload(existing=None):
        payload = {}
        for key in request_field_keys:
            default_value = ""
            if existing is not None:
                if hasattr(existing, "keys") and key in existing.keys():
                    value = existing[key]
                else:
                    value = ""
                default_value = "" if value is None else str(value)
            payload[key] = request.form.get(key, default_value).strip()
        return payload

    # validate_fighter_request_payload has been consolidated into FighterRequestEngine.

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            conn = db()
            user = conn.execute("SELECT * FROM users WHERE username=?", (request.form.get("username", "").strip(),)).fetchone()
            if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
                if not is_site_admin(user):
                    memberships = eligible_memberships(conn, user["id"])
                    if not memberships:
                        flash("That league is not currently active. Please contact the site admin.")
                        return render_template("login.html"), 403
                session.clear()
                session["user_id"] = user["id"]
                if is_site_admin(user):
                    session["active_league_id"] = user["league_id"]
                else:
                    memberships = eligible_memberships(conn, user["id"])
                    if len(memberships) == 1:
                        session["active_league_id"] = memberships[0]["league_id"]
                    else:
                        session["pending_league_selection"] = True
                csrf_token()
                flash(f"Logged in as {user['display_name']}.")
                if not is_site_admin(user) and len(memberships) > 1:
                    return redirect(url_for("select_league"))
                return post_login_redirect(user)
            flash("Invalid username or password.")
        return render_template("login.html")

    @app.route("/claim", methods=["GET", "POST"])
    def claim_code():
        if request.method == "POST":
            code = request.form.get("code", "").strip().upper()
            row = db().execute(
                """
                SELECT token
                FROM claim_tokens
                WHERE code=? AND used_at IS NULL AND expires_at >= ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (code, now_iso()),
            ).fetchone()
            if row:
                return redirect(url_for("claim_account", token=row["token"]))
            flash("That claim code is invalid or expired.")
        return render_template("claim_code.html")

    @app.route("/claim/<token>", methods=["GET", "POST"])
    def claim_account(token):
        conn = db()
        claim = conn.execute(
            """
            SELECT ct.*, u.username, u.display_name, u.claimed_at,
                   l.name AS league_name, l.club_name AS league_club_name, l.status AS league_status
            FROM claim_tokens ct
            JOIN users u ON u.id = ct.user_id
            LEFT JOIN leagues l ON l.id = ct.league_id
            WHERE ct.token=?
            """,
            (token,),
        ).fetchone()
        if not claim:
            deps["abort"](404)
        membership = None
        if claim["league_id"]:
            membership = conn.execute(
                """
                SELECT *
                FROM league_memberships
                WHERE user_id=? AND league_id=?
                ORDER BY id DESC
                LIMIT 1
                """,
                (claim["user_id"], claim["league_id"]),
            ).fetchone()
        if claim["league_id"] and not membership:
            flash("This claim link no longer matches your assigned league.")
            return redirect(url_for("login"))
        if claim["used_at"] or claim["expires_at"] < now_iso():
            flash("This claim link has expired.")
            return redirect(url_for("login"))
        if request.method == "POST":
            display_name = request.form.get("display_name", "").strip()
            password = request.form.get("password", "")
            if not display_name:
                flash("Display name is required.")
                return render_template("claim_account.html", claim=claim), 400
            if not password:
                flash("Choose a password to finish claiming this account.")
                return render_template("claim_account.html", claim=claim), 400
            if get_ops_engine:
                try:
                    ops_engine = get_ops_engine(conn)
                    ops_engine.tokens.execute_claim(token, display_name, password)
                    conn.commit()
                except ValidationError as exc:
                    conn.rollback()
                    flash(str(exc))
                    return render_template("claim_account.html", claim=claim), 400
            else:
                conn.execute(
                    "UPDATE users SET display_name=?, password_hash=?, claimed_at=? WHERE id=?",
                    (display_name, generate_password_hash(password), now_iso(), claim["user_id"]),
                )
                conn.execute("UPDATE claim_tokens SET used_at=? WHERE id=?", (now_iso(), claim["id"]))
                log_audit(conn, "user", claim["user_id"], "claim", f"Player account claimed by {display_name}.", rollback_type=None)
                create_notification(conn, "Manager joined the league", f"{display_name} has claimed their team account.", "success")
                conn.commit()
            session.clear()
            session["user_id"] = claim["user_id"]
            session["active_league_id"] = claim["league_id"]
            csrf_token()
            flash("Account claimed. You're now signed in.")
            return redirect(url_for("my_team"))
        return render_template("claim_account.html", claim=claim)

    @app.post("/logout")
    def logout():
        session.clear()
        csrf_token()
        flash("Logged out.")
        return redirect(url_for("index"))

    @app.route("/select-league", methods=["GET", "POST"])
    @login_required
    def select_league():
        user = current_user()
        if is_site_admin(user):
            return redirect(url_for(admin_dashboard_endpoint))
        conn = db()
        memberships = eligible_memberships(conn, user["id"])
        if not memberships:
            flash("That league is not currently active. Please contact the site admin.")
            return redirect(url_for("login"))
        if len(memberships) == 1:
            session["active_league_id"] = memberships[0]["league_id"]
            session.pop("pending_league_selection", None)
            return post_login_redirect(user)
        if request.method == "POST":
            raw_league_id = request.form.get("league_id", "").strip()
            if not raw_league_id:
                flash("Choose a league to continue.")
                return render_template("select_league.html", memberships=memberships), 400
            try:
                league_id = int(raw_league_id)
            except ValueError:
                flash("Choose a valid league to continue.")
                return render_template("select_league.html", memberships=memberships), 400
            membership = next((row for row in memberships if row["league_id"] == league_id), None)
            if not membership:
                flash("You do not have access to that league.")
                return render_template("select_league.html", memberships=memberships), 403
            session["active_league_id"] = league_id
            session.pop("pending_league_selection", None)
            flash(f"Switched to {membership['league_name']}.")
            return post_login_redirect(user)
        return render_template("select_league.html", memberships=memberships)

    @app.post("/switch-league")
    @login_required
    def switch_league():
        user = current_user()
        if is_site_admin(user):
            abort(403)
        raw_league_id = request.form.get("league_id", "").strip()
        if not raw_league_id:
            flash("Choose a league to switch into.")
            return redirect(request.referrer or url_for("index"))
        try:
            league_id = int(raw_league_id)
        except ValueError:
            flash("Choose a valid league.")
            return redirect(request.referrer or url_for("index"))
        conn = db()
        membership = conn.execute(
            """
            SELECT lm.*, l.name AS league_name, l.status AS league_status
            FROM league_memberships lm
            JOIN leagues l ON l.id = lm.league_id
            WHERE lm.user_id=? AND lm.league_id=? AND lm.status='active'
            LIMIT 1
            """,
            (user["id"], league_id),
        ).fetchone()
        if not membership:
            flash("You do not have access to that league.")
            return redirect(request.referrer or url_for("index"))
        if membership["league_status"] != "active":
            flash("That league is not currently active. Please contact the site admin.")
            return redirect(request.referrer or url_for("index"))
        session["active_league_id"] = league_id
        session.pop("pending_league_selection", None)
        flash(f"Switched to {membership['league_name']}.")
        if is_admin_user(user):
            return redirect(request.referrer or url_for(admin_home_endpoint))
        return redirect(request.referrer or url_for("my_team"))

    @app.route("/join-league", methods=["GET", "POST"])
    @login_required
    def join_league():
        user = current_user()
        if is_site_admin(user):
            abort(403)
        if request.method == "POST":
            code = request.form.get("code", "").strip().upper()
            if not code:
                flash("Enter a valid join code.")
                return render_template("join_league.html"), 400
            conn = db()
            try:
                league = conn.execute(
                    "SELECT * FROM leagues WHERE join_code=?",
                    (code,),
                ).fetchone()
                if not league:
                    flash("That join code is invalid.")
                    return render_template("join_league.html"), 400
                if league["status"] != "active":
                    flash("That league is not currently active.")
                    return render_template("join_league.html"), 400
                existing = conn.execute(
                    """
                    SELECT *
                    FROM league_memberships
                    WHERE user_id=? AND league_id=?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (user["id"], league["id"]),
                ).fetchone()
                if existing and existing["status"] == "active":
                    session["active_league_id"] = league["id"]
                    flash(f"You're already a member of {league['name']}.")
                    return redirect(url_for("index"))
                require_player_capacity(conn, league["id"])
                ensure_active_league_membership(
                    conn,
                    user["id"],
                    league["id"],
                    role=existing["role"] if existing and existing["role"] == "league_admin" else "player",
                    manager_limit=max(1, int(existing["manager_limit"] or 0)) if existing else 1,
                )
                membership = conn.execute(
                    """
                    SELECT *
                    FROM league_memberships
                    WHERE user_id=? AND league_id=?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (user["id"], league["id"]),
                ).fetchone()
                log_audit(
                    conn,
                    "league_membership",
                    membership["id"] if membership else None,
                    "join",
                    f"{user['display_name']} joined {league['name']} with a league join code.",
                    after_state={"league_id": league["id"], "role": membership["role"] if membership else "player"},
                    league_id=league["id"],
                )
                conn.commit()
                session["active_league_id"] = league["id"]
                flash(f"You joined {league['name']}.")
                if is_admin_user(user) and not can_manage_teams_in_active_league(user, conn):
                    return redirect(url_for(admin_home_endpoint))
                return redirect(url_for("my_team"))
            except ValidationError as exc:
                flash(str(exc))
                return render_template("join_league.html"), 400
        return render_template("join_league.html")

    @app.route("/fighters/<int:fighter_id>/request-edit", methods=["GET", "POST"])
    @login_required
    def request_fighter_edit(fighter_id):
        user = current_user()
        if is_site_admin(user):
            abort(403)
        conn = db()
        league = league_for_user(user, conn)
        if not league:
            abort(403)
        fighter = conn.execute(
            "SELECT * FROM fighters WHERE id=? AND league_id=?",
            (fighter_id, league["id"]),
        ).fetchone()
        if not fighter:
            abort(404)
        if request.method == "POST":
            try:
                payload = fighter_request_payload(fighter)
                
                request_id = FighterRequestEngine(conn).create_proposal(
                    user_id=user["id"],
                    league_id=league["id"],
                    request_type="edit",
                    payload=payload,
                    fighter_id=fighter_id,
                )
                log_audit(
                    conn,
                    "fighter_change_request",
                    request_id,
                    "create",
                    f"{user['display_name']} submitted a fighter edit request for {fighter['name']}.",
                    after_state={"request_type": "edit", "fighter_id": fighter_id, "league_id": league["id"]},
                    league_id=league["id"],
                )
                create_notification(
                    conn,
                    "Fighter edit request submitted",
                    f"{user['display_name']} submitted a fighter edit request for {fighter['name']}.",
                    "update",
                )
                conn.commit()
                flash("Fighter update request submitted.")
                return redirect(url_for("fighter_detail", fighter_id=fighter_id))
            except ValidationError as exc:
                flash(str(exc))
                return render_template("fighter_request_form.html", mode="edit", fighter=fighter, values=fighter_request_payload(fighter), league=league), 400
        return render_template("fighter_request_form.html", mode="edit", fighter=fighter, values=fighter_request_payload(fighter), league=league)

    @app.route("/fighters/request-new", methods=["GET", "POST"])
    @login_required
    def request_new_fighter():
        user = current_user()
        if is_site_admin(user):
            abort(403)
        conn = db()
        league = league_for_user(user, conn)
        if not league:
            abort(403)
        if request.method == "POST":
            try:
                payload = fighter_request_payload()
                
                request_id = FighterRequestEngine(conn).create_proposal(
                    user_id=user["id"],
                    league_id=league["id"],
                    request_type="create",
                    payload=payload,
                )
                log_audit(
                    conn,
                    "fighter_change_request",
                    request_id,
                    "create",
                    f"{user['display_name']} submitted a new fighter request for {payload['name']}.",
                    after_state={"request_type": "create", "name": payload["name"], "league_id": league["id"]},
                    league_id=league["id"],
                )
                create_notification(
                    conn,
                    "New fighter request submitted",
                    f"{user['display_name']} submitted a request for a new fighter: {payload['name']}.",
                    "update",
                )
                conn.commit()
                flash("New fighter request submitted.")
                return redirect(url_for("fighters"))
            except ValidationError as exc:
                flash(str(exc))
                return render_template("fighter_request_form.html", mode="create", fighter=None, values=fighter_request_payload(), league=league), 400
        return render_template("fighter_request_form.html", mode="create", fighter=None, values=fighter_request_payload(), league=league)

    @app.route("/my-notifications")
    @login_required
    def my_notifications():
        user = current_user()
        if is_site_admin(user):
            abort(403)
        conn = db()
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT
                    fcr.*,
                    f.name AS fighter_name,
                    l.name AS league_name,
                    rv.display_name AS reviewer_name
                FROM fighter_change_requests fcr
                LEFT JOIN fighters f ON f.id = fcr.fighter_id
                LEFT JOIN leagues l ON l.id = fcr.league_id
                LEFT JOIN users rv ON rv.id = fcr.reviewed_by_user_id
                WHERE fcr.requester_user_id=?
                ORDER BY
                    CASE fcr.status
                        WHEN 'pending' THEN 0
                        WHEN 'approved' THEN 1
                        ELSE 2
                    END,
                    fcr.updated_at DESC,
                    fcr.id DESC
                """,
                (user["id"],),
            ).fetchall()
        ]
        for row in rows:
            payload = json.loads(row["payload_json"])
            row["payload"] = payload
            row["request_target"] = row["fighter_name"] or payload.get("name") or "New fighter"
        rows, toolbar = apply_collection_filters(
            rows,
            search_fields=["request_target", "league_name", "status", "request_type", "review_notes"],
            filters=[
                {"name": "status", "label": "Status", "field": "status"},
                {"name": "type", "label": "Type", "field": "request_type"},
                {"name": "league", "label": "League", "field": "league_name"},
            ],
            sort_options=[
                {"value": "default", "label": "Pending First"},
                {"value": "latest", "label": "Latest Activity", "key": lambda row: row["updated_at"], "reverse": True},
                {"value": "submitted", "label": "Submitted First", "key": lambda row: row["created_at"], "reverse": True},
            ],
            search_placeholder="Search requests, leagues, or review notes",
        )
        return render_template("my_notifications.html", rows=rows, toolbar=toolbar)

    @app.route("/dashboard")
    @login_required
    def player_dashboard():
        user = current_user()
        if is_site_admin(user) or is_admin_user(user):
            return redirect(url_for(admin_home_endpoint if not is_site_admin(user) else admin_dashboard_endpoint))
        conn = db()
        league = league_for_user(user, conn)
        managed_ids = {team["id"] for team in teams_for_player(conn, user["id"])}
        rows = [row for row in team_rows(conn) if row["id"] in managed_ids]
        team = rows[0] if rows else None
        slot_usage = player_manager_slot_usage(conn, user["id"])
        landing = home_payload(conn)
        next_tournament = landing.get("next_tournament")
        latest_event_results = landing.get("latest_event_results")
        own_latest_gain = team["event_history"][0] if team and team.get("event_history") else None
        if next_tournament:
            deadline_label = next_tournament.get("date")
            deadline_context = next_tournament.get("name")
        else:
            deadline_label = "No live event published"
            deadline_context = "No roster lock cue is available yet."
        return render_template(
            "player_dashboard.html",
            player=user,
            player_league=league,
            team=team,
            slot_usage=slot_usage,
            next_tournament=next_tournament,
            latest_event_results=latest_event_results,
            own_latest_gain=own_latest_gain,
            deadline_label=deadline_label,
            deadline_context=deadline_context,
        )

    @app.route("/my-team")
    @login_required
    def my_team():
        user = current_user()
        conn = db()
        if is_admin_user(user) and not can_manage_teams_in_active_league(user, conn):
            return redirect(url_for(admin_home_endpoint if not is_site_admin(user) else teams_endpoint))
        managed_ids = {team["id"] for team in teams_for_player(conn, user["id"])}
        rows = [row for row in team_rows(conn) if row["id"] in managed_ids]
        slot_usage = player_manager_slot_usage(conn, user["id"])
        return render_template("my_teams.html", rows=rows, player=user, player_league=league_for_user(user, conn), slot_usage=slot_usage)

    @app.route("/my-team/new", methods=["GET", "POST"])
    @login_required
    def player_team_new():
        user = current_user()
        conn = db()
        if is_admin_user(user) and not can_manage_teams_in_active_league(user, conn):
            return redirect(url_for(admin_team_new_endpoint))
        slot_usage = player_manager_slot_usage(conn, user["id"])
        if not slot_usage or slot_usage["limit"] <= 0:
            flash("Team creation is not enabled for your account in this league.")
            return redirect(url_for("my_team"))
        if slot_usage["used"] >= slot_usage["limit"]:
            flash("You already have a team in this league.")
            return redirect(url_for("my_team"))
        if request.method == "POST":
            try:
                team_id = save_team(forced_player_user_id=user["id"])
            except ValidationError as exc:
                flash(str(exc))
                selected = [
                    parse_int_field_from_value("fighter_ids", raw.strip(), minimum=1)
                    for raw in request.form.getlist("fighter_ids")
                    if raw.strip().isdigit()
                ]
                context = team_builder_context(conn)
                return render_template(
                    "admin_team_form.html",
                    team={
                        "team_name": request.form.get("team_name", "").strip(),
                        "manager": request.form.get("manager", "").strip(),
                        "player_user_id": user["id"],
                        "image_credit": request.form.get("image_credit", "").strip(),
                        "image_source_url": request.form.get("image_source_url", "").strip(),
                    },
                    selected=selected,
                    show_player_select=False,
                    builder_owner=user,
                    **context,
                ), 400
            flash("Team created.")
            return redirect(url_for(team_detail_endpoint, team_id=team_id))
        context = team_builder_context(conn)
        return render_template(
            "admin_team_form.html",
            team={"player_user_id": user["id"], "manager": user["display_name"]},
            selected=[],
            show_player_select=False,
            builder_owner=user,
            **context,
        )
