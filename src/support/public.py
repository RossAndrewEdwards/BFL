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
    
    def _movement(previous_rank, current_rank):
        if not current_rank:
            return None
        if previous_rank is None:
            return {
                "previous_rank": None,
                "current_rank": current_rank,
                "direction": "new",
                "delta": 0,
                "label": "New",
            }
        if previous_rank > current_rank:
            delta = previous_rank - current_rank
            return {
                "previous_rank": previous_rank,
                "current_rank": current_rank,
                "direction": "up",
                "delta": delta,
                "label": f"Up {delta}",
            }
        if previous_rank < current_rank:
            delta = current_rank - previous_rank
            return {
                "previous_rank": previous_rank,
                "current_rank": current_rank,
                "direction": "down",
                "delta": delta,
                "label": f"Down {delta}",
            }
        return {
            "previous_rank": previous_rank,
            "current_rank": current_rank,
            "direction": "stay",
            "delta": 0,
            "label": "Held",
        }

    def load():
        from src.support.auth import scoped_league_id
        league_id = league_id_override if league_id_override is not None else scoped_league_id()
        event = conn.execute(
            """
            SELECT er.scheduled_event_id,
                   er.event_date,
                   er.event_name,
                   COUNT(*) AS result_count,
                   eb.headline,
                   eb.subheading
            FROM event_results er
            LEFT JOIN event_banners eb ON eb.id = er.scheduled_event_id
            WHERE (? IS NULL OR er.league_id=?)
            GROUP BY er.scheduled_event_id, er.event_date, er.event_name
            ORDER BY er.event_date DESC, MAX(er.id) DESC
            LIMIT 1
            """,
            (league_id, league_id),
        ).fetchone()
        if not event:
            return None

        event = dict(event)
        from src.app import rules_dict, leaderboard_rows, event_points, tier_theme, PUBLIC_PROFILE_STAT_ORDER, event_summary_text
        
        rules = rules_dict(conn)
        leaderboard_lookup = {row["id"]: row for row in leaderboard_rows(conn)}
        fighter_rows = []
        fighter_results = conn.execute(
            """
            SELECT er.*,
                   f.name,
                   f.tier,
                   f.nickname,
                   f.preferred_role,
                   f.fighting_style,
                   f.image_url,
                   f.image_credit,
                   f.image_source_url
            FROM event_results er
            JOIN fighters f ON f.id = er.fighter_id
            WHERE ((er.scheduled_event_id = ?) OR (? IS NULL AND er.scheduled_event_id IS NULL AND er.event_date = ? AND er.event_name = ?))
              AND (? IS NULL OR er.league_id=?)
            ORDER BY f.name
            """,
            (event.get("scheduled_event_id"), event.get("scheduled_event_id"), event["event_date"], event["event_name"], league_id, league_id),
        ).fetchall()
        for row in fighter_results:
            fighter = dict(row)
            fighter.update(
                {
                    key: leaderboard_lookup.get(fighter["fighter_id"], {}).get(key, 0)
                    for key, _label in PUBLIC_PROFILE_STAT_ORDER
                }
            )
            fighter["overall_rating"] = leaderboard_lookup.get(fighter["fighter_id"], {}).get("overall_rating", 0)
            fighter["event_points"] = event_points(fighter, rules)
            fighter["tier_theme"] = tier_theme(fighter.get("tier"))
            fighter_rows.append(fighter)
        fighter_rows.sort(key=lambda row: (-row["event_points"], row["name"]))
        for index, row in enumerate(fighter_rows, start=1):
            row["event_rank"] = index
            row["public_display"] = public_event_fighter_display(row)

        fighter_event_points = {row["fighter_id"]: int(row["event_points"] or 0) for row in fighter_rows}
        previous_fighter_rows = []
        for leaderboard_row in leaderboard_lookup.values():
            previous_total = int(leaderboard_row.get("total_points") or 0) - fighter_event_points.get(leaderboard_row["id"], 0)
            previous_fighter_rows.append((leaderboard_row["id"], previous_total, leaderboard_row.get("name", "")))
        previous_fighter_rows.sort(key=lambda row: (-row[1], row[2].lower(), row[0]))
        previous_fighter_ranks = {fighter_id: index for index, (fighter_id, _points, _name) in enumerate(previous_fighter_rows, start=1)}
        for row in fighter_rows:
            current_rank = leaderboard_lookup.get(row["fighter_id"], {}).get("rank")
            row["movement"] = _movement(previous_fighter_ranks.get(row["fighter_id"]), current_rank)

        team_entries = []
        from src.app import team_rows
        all_teams = team_rows(conn)
        fighter_points = {row["fighter_id"]: row["event_points"] for row in fighter_rows}
        for team in all_teams:
            event_total = sum(fighter_points.get(fighter["id"], 0) for fighter in team["fighters"])
            if event_total <= 0:
                continue
            team_entry = dict(team)
            team_entry["event_points"] = event_total
            team_entry["event_fighter_count"] = sum(1 for fighter in team["fighters"] if fighter_points.get(fighter["id"], 0) > 0)
            team_entries.append(team_entry)
        team_entries.sort(key=lambda row: (-row["event_points"], row["team_name"]))
        for index, row in enumerate(team_entries, start=1):
            row["event_rank"] = index

        previous_team_rows = []
        for team in all_teams:
            previous_total = int(team.get("points") or 0) - int(sum(fighter_points.get(fighter["id"], 0) for fighter in team["fighters"]) or 0)
            previous_team_rows.append((team["id"], previous_total, team.get("team_name", "")))
        previous_team_rows.sort(key=lambda row: (-row[1], row[2].lower(), row[0]))
        previous_team_ranks = {team_id: index for index, (team_id, _points, _name) in enumerate(previous_team_rows, start=1)}
        for row in team_entries:
            row["movement"] = _movement(previous_team_ranks.get(row["id"]), row.get("rank"))

        top_fighters = fighter_rows[:3]
        top_teams = team_entries[:3]
        best_team = top_teams[0] if top_teams else None
        fighter_movers = sorted(
            [row for row in fighter_rows if row.get("movement") and row["movement"]["direction"] == "up"],
            key=lambda row: (-row["movement"]["delta"], -row["event_points"], row["name"]),
        )
        team_movers = sorted(
            [row for row in team_entries if row.get("movement") and row["movement"]["direction"] == "up"],
            key=lambda row: (-row["movement"]["delta"], -row["event_points"], row["team_name"]),
        )
        event["summary"] = event_summary_text(event, top_fighters, best_team)
        event["query_args"] = (
            {"scheduled_event_id": event["scheduled_event_id"]}
            if event.get("scheduled_event_id")
            else {"event_date": event["event_date"], "event_name": event["event_name"]}
        )
        return {
            "event": event,
            "top_fighters": top_fighters,
            "top_teams": top_teams,
            "best_team": best_team,
            "fighter_rows": fighter_rows,
            "team_rows": team_entries,
            "fighter_movers": fighter_movers,
            "team_movers": team_movers,
        }

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
