def public_event_fighter_display(fighter):
    from src.app import public_fighter_display
    display = public_fighter_display({"rank": fighter.get("event_rank"), **fighter}, context="event")
    
    from src.app import public_fighter_spotlight_label
    return {
        "spotlight_label": public_fighter_spotlight_label({"rank": fighter.get("event_rank")}, context="leaderboard"),
        "summary": display["summary"],
        "stats": display["stats"],
    }


def latest_event_results_payload(conn, league_id_override=None):
    from src.app import request_cached

    def load():
        from src.engine.performance import FighterPerformanceEngine
        return FighterPerformanceEngine(conn).get_latest_event_payload(league_id_override)

    return request_cached("latest_event_results_payload", load)


def compare_team_payload(conn, team_a_id, team_b_id):
    from src.app import team_rows, leaderboard_rows
    rows = {row["id"]: row for row in team_rows(conn)}
    team_a = rows.get(team_a_id)
    team_b = rows.get(team_b_id)
    if not team_a or not team_b:
        return None
    ids_a = {fighter["id"] for fighter in team_a["fighters"]}
    ids_b = {fighter["id"] for fighter in team_b["fighters"]}
    overlap_ids = ids_a & ids_b
    leaderboard = {row["id"]: row for row in leaderboard_rows(conn)}
    overlap = [leaderboard[fid] for fid in overlap_ids if fid in leaderboard]
    return {
        "team_a": team_a,
        "team_b": team_b,
        "overlap": sorted(overlap, key=lambda row: row["name"]),
        "only_a": [leaderboard[fid] for fid in ids_a - ids_b if fid in leaderboard],
        "only_b": [leaderboard[fid] for fid in ids_b - ids_a if fid in leaderboard],
        "projection_a": team_a["points"],
        "projection_b": team_b["points"],
    }


def home_payload(conn, landing_images):
    from src.app import upcoming_buhurt_uk_tournaments, latest_event_results_payload
    from src.support.auth import effective_league_id
    tournaments = upcoming_buhurt_uk_tournaments(conn)
    latest_event = latest_event_results_payload(conn, league_id_override=effective_league_id())
    return {
        "next_tournament": tournaments[0] if tournaments else None,
        "upcoming_tournaments": tournaments[1:] if len(tournaments) > 1 else [],
        "latest_event_results": latest_event,
        "landing_images": landing_images,
    }
