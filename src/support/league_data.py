class defaultdict_int(dict):
    def __missing__(self, key):
        self[key] = 0
        return 0


def migrate_attendance_scores_to_baseline(conn):
    rows = conn.execute(
        """
        SELECT fighter_id, score_type, SUM(score_units) AS total_units
        FROM attendance_scores
        WHERE score_type IN ('training', 'support')
        GROUP BY fighter_id, score_type
        """
    ).fetchall()
    if rows:
        totals_by_fighter = {}
        for row in rows:
            entry = totals_by_fighter.setdefault(row["fighter_id"], {"training": 0, "support": 0})
            entry[row["score_type"]] = int(row["total_units"] or 0)
        for fighter_id, totals in totals_by_fighter.items():
            conn.execute(
                """
                INSERT INTO baseline_stats(fighter_id, training, support)
                VALUES(?,?,?)
                ON CONFLICT(fighter_id) DO UPDATE SET
                    training=baseline_stats.training + excluded.training,
                    support=baseline_stats.support + excluded.support
                """,
                (fighter_id, totals["training"], totals["support"]),
            )
        conn.execute("DELETE FROM attendance_scores WHERE score_type IN ('training', 'support')")


def _fighter_to_dict(f):
    kd_ratio = f.kills / max(1, f.deaths)
    discipline_score = f.training + f.competitions + f.support - f.sit_downs - f.yellow_cards - f.red_cards
    fame_score = f.gold_medals * 3 + f.silver_medals * 2 + f.bronze_medals + f.competitions
    res = dict(f.profile_fields) if hasattr(f, "profile_fields") and f.profile_fields else {}
    res.update({
        "id": f.fighter_id,
        "name": f.name,
        "tier": f.tier,
        "rank": f.rank,
        "total_points": f.total_points,
        "current_cost": f.current_cost,
        "next_season_cost": f.next_season_cost,
        "overall_rating": f.overall_rating,
        "glory": f.glory,
        "discipline_rating": f.discipline,
        "discipline_score": discipline_score,
        "lethality": f.lethality,
        "resilience": f.resilience,
        "crowd_favourite": f.crowd_favourite,
        "synergy": f.synergy,
        "competitions": f.competitions,
        "rounds_fought": f.rounds_fought,
        "kills": f.kills,
        "deaths": f.deaths,
        "assists": f.assists,
        "gold_medals": f.gold_medals,
        "silver_medals": f.silver_medals,
        "bronze_medals": f.bronze_medals,
        "special_awards": f.special_awards,
        "training": f.training,
        "support": f.support,
        "yellow_cards": f.yellow_cards,
        "red_cards": f.red_cards,
        "sit_downs": f.sit_downs,
        "ownership_percent": f.ownership_percent,
        "tier_theme": f.tier_theme,
        "kd_ratio": kd_ratio,
        "fame_score": fame_score,
        "baseline_training": f.training,
        "baseline_support": f.support,
        "attendance_training": 0,
        "attendance_support": 0,
        "recent_training_date": None,
        "recent_support_date": None,
        "league_id": f.league_id,
    })
    return res


def _team_to_dict(t, settings):
    try:
        budget = int(float(settings.get("team_budget", 500)))
    except Exception:
        budget = 500
        
    use_next = settings.get("cost_mode") == "Next Season"
    cost = sum(f.next_season_cost if use_next else f.current_cost for f in t.fighters)
    
    return {
        "id": t.team_id,
        "team_name": t.team_name,
        "manager": t.manager,
        "player_user_id": t.player_user_id,
        "player_name": t.player_name,
        "image_path": t.image_path,
        "image_credit": t.image_credit,
        "image_source_url": t.image_source_url,
        "points": t.points,
        "rank": t.rank,
        "status": t.status,
        "fighters": [_fighter_to_dict(f) for f in t.fighters],
        "trait_totals": t.trait_totals,
        "event_history": t.event_history,
        "league_id": t.league_id,
        "member_count": len(t.fighters),
        "cost": cost,
        "remaining": budget - cost,
    }


def fighter_aggregates(conn, *, request_cached_fn, scoped_league_id_fn):
    def load():
        from src.engine.roster import RosterRankingsEngine
        league_id = scoped_league_id_fn(conn)
        leaderboard = RosterRankingsEngine.get_fighter_leaderboard(conn, league_id)
        return {
            f.fighter_id: {
                "fighter_id": f.fighter_id,
                "competitions": f.competitions,
                "rounds_fought": f.rounds_fought,
                "special_awards": f.special_awards,
                "gold_medals": f.gold_medals,
                "silver_medals": f.silver_medals,
                "bronze_medals": f.bronze_medals,
                "kills": f.kills,
                "assists": f.assists,
                "deaths": f.deaths,
                "sit_downs": f.sit_downs,
                "yellow_cards": f.yellow_cards,
                "red_cards": f.red_cards,
            }
            for f in leaderboard
        }
    return request_cached_fn("fighter_aggregates", load)


def fighter_ownership_rates(conn, *, request_cached_fn, scoped_league_id_fn):
    def load():
        from src.engine.roster import RosterRankingsEngine
        league_id = scoped_league_id_fn(conn)
        leaderboard = RosterRankingsEngine.get_fighter_leaderboard(conn, league_id)
        return {f.fighter_id: f.ownership_percent for f in leaderboard}
    return request_cached_fn("fighter_ownership_rates", load)


def fighter_import_totals(conn, *, request_cached_fn, scoped_league_id_fn):
    def load():
        league_id = scoped_league_id_fn(conn)
        rows = conn.execute(
            """
            SELECT fit.*
            FROM fighter_import_totals fit
            JOIN fighters f ON f.id = fit.fighter_id
            WHERE (? IS NULL OR f.league_id=?)
            """,
            (league_id, league_id),
        ).fetchall()
        return {row["fighter_id"]: dict(row) for row in rows}
    return request_cached_fn("fighter_import_totals", load)


def attendance_score_aggregates(conn, *, request_cached_fn, scoped_league_id_fn):
    def load():
        league_id = scoped_league_id_fn(conn)
        rows = conn.execute(
            """
            SELECT a.fighter_id,
                   a.score_type,
                   SUM(a.score_units) AS total_units,
                   MAX(a.attendance_date) AS latest_date
            FROM attendance_scores a
            JOIN fighters f ON f.id = a.fighter_id
            WHERE (? IS NULL OR f.league_id=?)
            GROUP BY fighter_id, score_type
            """,
            (league_id, league_id),
        ).fetchall()
        by_fighter = {}
        for row in rows:
            fighter_entry = by_fighter.setdefault(
                row["fighter_id"],
                {
                    "training": 0,
                    "support": 0,
                    "recent_training_date": None,
                    "recent_support_date": None,
                },
            )
            if row["score_type"] == "training":
                fighter_entry["training"] = int(row["total_units"] or 0)
                fighter_entry["recent_training_date"] = row["latest_date"]
            elif row["score_type"] == "support":
                fighter_entry["support"] = int(row["total_units"] or 0)
                fighter_entry["recent_support_date"] = row["latest_date"]
        return by_fighter
    return request_cached_fn("attendance_score_aggregates", load)


def raw_fighter_stats(
    conn,
    *,
    request_cached_fn,
    fighter_aggregates_fn,
    fighter_import_totals_fn,
    fighter_ownership_rates_fn,
    scoped_league_id_fn,
    rules_dict_fn,
    tier_theme_fn,
    apply_public_profile_ratings_fn,
    stat_keys,
    fighter_result_extra_keys,
):
    def load():
        from src.engine.roster import RosterRankingsEngine
        league_id = scoped_league_id_fn(conn)
        leaderboard = RosterRankingsEngine.get_fighter_leaderboard(conn, league_id)
        return [_fighter_to_dict(f) for f in leaderboard]
    return request_cached_fn("raw_fighter_stats", load)


def fighter_admin_totals(conn, fighter_id, *, raw_fighter_stats_fn):
    for row in raw_fighter_stats_fn(conn):
        if row["id"] == fighter_id:
            return row
    return None


def current_cost_map(conn, *, request_cached_fn, scoped_league_id_fn):
    league_id = scoped_league_id_fn(conn)
    return request_cached_fn(
        "current_cost_map",
        lambda: {
            row["id"]: int(row["current_cost"] or 0)
            for row in conn.execute(
                "SELECT id,current_cost FROM fighters WHERE (? IS NULL OR league_id=?)",
                (league_id, league_id),
            )
        },
    )


def get_team_selections(conn, *, request_cached_fn, scoped_league_id_fn):
    def load():
        league_id = scoped_league_id_fn(conn)
        teams = conn.execute(
            """
            SELECT ft.*, u.display_name AS player_name, u.username AS player_username
            FROM fantasy_teams ft
            LEFT JOIN users u ON u.id = ft.player_user_id
            WHERE (? IS NULL OR ft.league_id=?)
            ORDER BY ft.team_name
            """,
            (league_id, league_id),
        ).fetchall()
        selected = {team["id"]: [] for team in teams}
        if teams:
            rows = conn.execute(
                """
                SELECT ftf.team_id, ftf.slot, f.*
                FROM fantasy_team_fighters ftf
                JOIN fantasy_teams ft ON ft.id = ftf.team_id
                JOIN fighters f ON f.id = ftf.fighter_id
                WHERE (? IS NULL OR ft.league_id=?)
                ORDER BY ftf.team_id, ftf.slot
                """,
                (league_id, league_id),
            ).fetchall()
            for row in rows:
                selected.setdefault(row["team_id"], []).append(row)
        return teams, selected
    return request_cached_fn("team_selections", load)


def ownership_next_costs(
    conn,
    *,
    request_cached_fn,
    current_season_fn,
    settings_dict_fn,
    current_cost_map_fn,
    get_team_selections_fn,
    validate_team_fn,
    base_cost_for_tier_fn,
    scoped_league_id_fn,
):
    def load():
        from src.engine.roster import RosterRankingsEngine
        league_id = scoped_league_id_fn(conn)
        settings = settings_dict_fn(conn)
        return RosterRankingsEngine._calculate_next_season_costs(conn, league_id, settings)
    return request_cached_fn("ownership_next_costs", load)


def leaderboard_rows(
    conn,
    *,
    request_cached_fn,
    settings_dict_fn,
    ownership_next_costs_fn,
    raw_fighter_stats_fn,
):
    def load():
        settings = settings_dict_fn(conn)
        next_costs = ownership_next_costs_fn(conn)
        rows = [dict(row) for row in raw_fighter_stats_fn(conn)]
        use_next = settings.get("cost_mode") == "Next Season"
        for row in rows:
            row["next_cost"] = next_costs.get(row["id"], row["current_cost"])
            row["cost_used"] = row["next_cost"] if use_next else row["current_cost"]
        return rows
    return request_cached_fn("leaderboard_rows", load)


def team_rows(
    conn,
    *,
    request_cached_fn,
    settings_dict_fn,
    rules_dict_fn,
    leaderboard_rows_fn,
    get_team_selections_fn,
    validate_team_fn,
    event_points_fn,
):
    def load():
        from src.engine.roster import RosterRankingsEngine
        from src.support import auth as auth_support
        league_id = auth_support.scoped_league_id(conn)
        standings = RosterRankingsEngine.get_team_standings(conn, league_id)
        settings = settings_dict_fn(conn)
        return [_team_to_dict(t, settings) for t in standings]
    return request_cached_fn("team_rows", load)
