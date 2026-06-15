def register_public_routes(app, deps):
    abort = deps["abort"]
    apply_collection_filters = deps["apply_collection_filters"]
    compare_team_payload = deps["compare_team_payload"]
    current_user = deps["current_user"]
    db = deps["db"]
    event_points = deps["event_points"]
    filter_option_rows = deps["filter_option_rows"]
    get_or_create_share_token = deps["get_or_create_share_token"]
    hall_of_fame_data = deps["hall_of_fame_data"]
    home_payload = deps["home_payload"]
    latest_event_results_payload = deps["latest_event_results_payload"]
    leaderboard_rows = deps["leaderboard_rows"]
    login_required = deps["login_required"]
    public_fighter_affiliation = deps["public_fighter_affiliation"]
    public_fighter_display = deps["public_fighter_display"]
    public_top_fighter_label = deps["public_top_fighter_label"]
    public_profile_formula_groups = deps["public_profile_formula_groups"]
    render_template = deps["render_template"]
    request = deps["request"]
    rules_dict = deps["rules_dict"]
    scoped_league_id = deps["scoped_league_id"]
    settings_dict = deps["settings_dict"]
    team_rows = deps["team_rows"]
    url_for = deps["url_for"]
    redirect = deps["redirect"]
    FIGHTER_RESULT_EXTRA_KEYS = deps["FIGHTER_RESULT_EXTRA_KEYS"]
    STAT_KEYS = deps["STAT_KEYS"]

    def resolve_rival_team(all_team_rows, own_team):
        if not own_team:
            return None
        ranked_teams = [row for row in all_team_rows if row.get("rank")]
        if own_team in ranked_teams:
            own_index = ranked_teams.index(own_team)
            if own_index > 0:
                return ranked_teams[own_index - 1]
            if own_index + 1 < len(ranked_teams):
                return ranked_teams[own_index + 1]
        other_teams = [row for row in all_team_rows if row.get("id") != own_team.get("id")]
        if not other_teams:
            return None
        return min(
            other_teams,
            key=lambda row: (
                abs(int(row.get("points") or 0) - int(own_team.get("points") or 0)),
                -(int(row.get("points") or 0)),
                row.get("team_name", "").lower(),
            ),
        )

    @app.route("/")
    def index():
        return render_template("home.html", **home_payload(db()))

    @app.route("/events/results")
    @login_required
    def public_event_results():
        payload = latest_event_results_payload(db())
        if payload is None:
            return render_template("event_results.html", event=None, top_fighters=[], top_teams=[], best_team=None), 200
        user = current_user()
        own_team = None
        rival_team = None
        if user:
            own_team = next((row for row in payload["team_rows"] if row.get("player_user_id") == user["id"]), None)
            rival_team = resolve_rival_team(payload["team_rows"], own_team)
        return render_template(
            "event_results.html",
            event=payload["event"],
            top_fighters=payload["fighter_rows"],
            top_teams=payload["team_rows"],
            best_team=payload["best_team"],
            fighter_movers=payload["fighter_movers"],
            team_movers=payload["team_movers"],
            own_team=own_team,
            rival_team=rival_team,
        )

    @app.route("/leaderboard")
    @login_required
    def leaderboard():
        conn = db()
        user = current_user()
        fighter_query = request.args.get("fighter_q", "").strip().lower()
        team_query = request.args.get("team_q", "").strip().lower()
        latest_event = latest_event_results_payload(conn)

        all_fighter_rows = sorted(
            leaderboard_rows(conn),
            key=lambda row: (-(int(row.get("total_points") or 0)), row.get("name", "").lower(), row.get("id", 0)),
        )
        for idx, row in enumerate(all_fighter_rows, start=1):
            row["rank"] = idx

        all_team_rows = sorted(
            team_rows(conn),
            key=lambda row: (-(int(row.get("points") or 0)), row.get("team_name", "").lower(), row.get("id", 0)),
        )

        fighter_rows = [
            row
            for row in all_fighter_rows
            if not fighter_query
            or fighter_query in (row.get("name", "").lower())
            or fighter_query in (str(row.get("nickname") or "").lower())
        ]
        team_list = [
            row
            for row in all_team_rows
            if not team_query
            or team_query in (row.get("team_name", "").lower())
            or team_query in (str(row.get("player_name") or "").lower())
        ]

        fighter_movement = {
            row["fighter_id"]: row.get("movement")
            for row in (latest_event.get("fighter_rows") if latest_event else [])
        }
        team_movement = {
            row["id"]: row.get("movement")
            for row in (latest_event.get("team_rows") if latest_event else [])
        }
        for row in fighter_rows:
            row["movement"] = fighter_movement.get(row["id"])
        for row in all_team_rows:
            row["movement"] = team_movement.get(row["id"])
        for row in team_list:
            row["movement"] = team_movement.get(row["id"])

        own_team = None
        rival_team = None
        if user:
            own_team = next((row for row in all_team_rows if row.get("player_user_id") == user["id"]), None)
            rival_team = resolve_rival_team(all_team_rows, own_team)

        leader_team = next((row for row in all_team_rows if row.get("rank") == 1), all_team_rows[0] if all_team_rows else None)
        fighter_leader = next((row for row in all_fighter_rows if row.get("rank") == 1), all_fighter_rows[0] if all_fighter_rows else None)
        return render_template(
            "leaderboard.html",
            fighter_rows=fighter_rows,
            team_rows=team_list,
            fighter_leader=fighter_leader,
            team_leader=leader_team,
            fighter_query=request.args.get("fighter_q", "").strip(),
            team_query=request.args.get("team_q", "").strip(),
            fighter_total_count=len(all_fighter_rows),
            team_total_count=len(all_team_rows),
            own_team=own_team,
            rival_team=rival_team,
            latest_event=latest_event["event"] if latest_event else None,
            fighter_movers=latest_event["fighter_movers"][:3] if latest_event else [],
            team_movers=latest_event["team_movers"][:3] if latest_event else [],
        )

    @app.route("/fighters")
    @login_required
    def fighters():
        all_rows = leaderboard_rows(db())
        tier_order = ["Tier 1", "Tier 2", "Tier 3", "Tier 4"]
        top_fighters = [
            row
            for row in all_rows
            if any(int(row.get(key) or 0) > 0 for key in STAT_KEYS + FIGHTER_RESULT_EXTRA_KEYS)
        ][:3]
        top_fighter_cards = []
        for row in top_fighters:
            card = dict(row)
            card["public_display"] = public_fighter_display(card, "leaderboard")
            card["public_display"]["spotlight_label"] = public_top_fighter_label(card.get("rank"))
            card["affiliation"] = public_fighter_affiliation(card)
            top_fighter_cards.append(card)
        tier_spotlights = []
        for tier_name in tier_order:
            tier_rows = [row for row in all_rows if row.get("tier") == tier_name]
            if not tier_rows:
                continue
            leader = tier_rows[0]
            tier_spotlights.append(
                {
                    "tier": tier_name,
                    "count": len(tier_rows),
                    "leader_name": leader.get("name"),
                    "leader_rank": leader.get("rank"),
                    "leader_points": leader.get("total_points") or 0,
                }
            )
        rows = all_rows
        rows, toolbar = apply_collection_filters(
            rows,
            search_fields=["name", "nickname", "preferred_role", "fighting_style", "tier", "notes", "bio"],
            filters=[
                {"name": "tier", "label": "Tier", "field": "tier"},
            ],
            sort_options=[
                {"value": "default", "label": "Rank"},
                {"value": "name", "label": "Name (A-Z)", "key": lambda row: row["name"]},
                {"value": "points", "label": "Points (High-Low)", "key": lambda row: row["total_points"], "reverse": True},
                {"value": "cost", "label": "Cost (High-Low)", "key": lambda row: row["cost_used"], "reverse": True},
            ],
            search_placeholder="Search fighters, tiers, roles, or styles",
        )
        browse_return_to = request.full_path if request.query_string else request.path
        return render_template(
            "fighters.html",
            rows=rows,
            toolbar=toolbar,
            top_fighter_cards=top_fighter_cards,
            tier_spotlights=tier_spotlights,
            browse_return_to=browse_return_to.rstrip("?"),
        )

    @app.route("/fighters/<int:fighter_id>")
    @login_required
    def fighter_detail(fighter_id):
        conn = db()
        rows = [r for r in leaderboard_rows(db()) if r["id"] == fighter_id]
        if not rows:
            abort(404)
        fighter = rows[0]
        league_id = scoped_league_id(conn)
        events = conn.execute(
            """
            SELECT *
            FROM event_results
            WHERE fighter_id=?
              AND (? IS NULL OR league_id=?)
            ORDER BY event_date DESC, event_name
            """,
            (fighter_id, league_id, league_id),
        ).fetchall()
        rules = rules_dict(conn)
        event_rows = []
        for event in events:
            row = dict(event)
            row["event_points"] = event_points(row, rules)
            event_rows.append(row)
        honours = conn.execute(
            """
            SELECT awarded_on, honour_type, units, title, notes
            FROM fighter_honours
            WHERE fighter_id=?
              AND (? IS NULL OR league_id=?)
            ORDER BY awarded_on DESC, id DESC
            """,
            (fighter_id, league_id, league_id),
        ).fetchall()
        browse_back_url = request.args.get("return_to", "").strip()
        if not browse_back_url.startswith("/fighters"):
            browse_back_url = url_for("fighters")
        return render_template(
            "fighter_detail.html",
            fighter=fighter,
            fighter_public_display=public_fighter_display(fighter, "leaderboard"),
            events=event_rows,
            honours=honours,
            browse_back_url=browse_back_url,
        )

    @app.route("/teams")
    @login_required
    def teams():
        rows = team_rows(db())
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
        return render_template("teams.html", rows=rows, toolbar=toolbar)

    @app.route("/teams/compare")
    @login_required
    def team_compare():
        conn = db()
        teams_list = team_rows(conn)
        comparison = None
        team_a = request.args.get("team_a", type=int)
        team_b = request.args.get("team_b", type=int)
        if team_a and team_b:
            comparison = compare_team_payload(conn, team_a, team_b)
            if comparison is None:
                abort(404)
        return render_template("team_compare.html", rows=teams_list, comparison=comparison, team_a=team_a, team_b=team_b)

    @app.route("/rules")
    def public_rules():
        conn = db()
        settings = settings_dict(conn)
        return render_template(
            "rules.html",
            rules=conn.execute("SELECT * FROM rules ORDER BY rowid").fetchall(),
            settings=settings,
            ownership_brackets=conn.execute("SELECT * FROM ownership_brackets ORDER BY lower_bound").fetchall(),
            public_profile_formula_groups=public_profile_formula_groups(settings),
        )

    @app.route("/contact")
    def contact():
        return render_template("contact.html")

    @app.route("/hall-of-fame")
    @login_required
    def hall_of_fame():
        conn = db()
        season_id = request.args.get("season", type=int)
        team_query = request.args.get("team", "").strip()
        fighter_query = request.args.get("fighter", "").strip()
        payload = hall_of_fame_data(conn, season_id, team_query, fighter_query)
        return render_template(
            "hall_of_fame.html",
            season_filter=season_id,
            team_filter=team_query,
            fighter_filter=fighter_query,
            **payload,
        )

    @app.route("/teams/<int:team_id>")
    @login_required
    def team_detail(team_id):
        rows = [r for r in team_rows(db()) if r["id"] == team_id]
        if not rows:
            abort(404)
        leaderboard = {r["id"]: r for r in leaderboard_rows(db())}
        share_token = get_or_create_share_token(db(), team_id)
        return render_template("team_detail.html", team=rows[0], leaderboard=leaderboard, share_token=share_token)

    @app.route("/share/team/<token>")
    @login_required
    def shared_team_detail(token):
        conn = db()
        row = conn.execute("SELECT team_id FROM team_share_links WHERE token=?", (token,)).fetchone()
        if not row:
            abort(404)
        rows = [r for r in team_rows(conn) if r["id"] == row["team_id"]]
        if not rows:
            abort(404)
        leaderboard = {r["id"]: r for r in leaderboard_rows(conn)}
        return render_template("shared_team_detail.html", team=rows[0], leaderboard=leaderboard)
