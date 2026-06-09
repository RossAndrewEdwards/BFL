import json
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from exceptions import ValidationError
from scoring_support import calculate_season_cost_changes, season_cost_settings_from_settings
from ops_support import log_audit, create_notification
from ui_support import query_text


def now_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat()


class SeasonLifecycleEngine:
    """
    Unified domain coordinator for season status,completed lists,
    leaderboard snapshotting, and pricing recalculations.
    """
    def __init__(self, conn):
        self._conn = conn

    def get_current_season(self) -> Optional[Dict[str, Any]]:
        season = self._conn.execute(
            """
            SELECT *
            FROM seasons
            WHERE status='active'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        if season:
            return season
        return self._conn.execute("SELECT * FROM seasons ORDER BY id DESC LIMIT 1").fetchone()

    def ensure_active_season(self) -> Dict[str, Any]:
        season = self._conn.execute(
            """
            SELECT *
            FROM seasons
            WHERE status='active'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        if season:
            return season
        existing_count = self._conn.execute("SELECT COUNT(*) AS c FROM seasons").fetchone()["c"]
        season_name = f"Season {existing_count + 1}"
        self._conn.execute(
            "INSERT INTO seasons(name,status,locked,started_at) VALUES(?, 'active', 0, ?)",
            (season_name, now_iso()),
        )
        self._conn.commit()
        return self._conn.execute("SELECT * FROM seasons WHERE id=last_insert_rowid()").fetchone()

    def get_lock_state(self) -> Tuple[Dict[str, Any], bool]:
        season = self.get_current_season()
        if not season:
            season = self.ensure_active_season()
        return season, bool(season["locked"]) or season["status"] != "active"

    def require_editable(self, action_label: str = "This action") -> Dict[str, Any]:
        season, locked = self.get_lock_state()
        if locked:
            season_name = season["name"] if season else "Current season"
            raise ValidationError(f"{action_label} is locked because {season_name} has already been ended.")
        return season

    def list_completed(self) -> List[Dict[str, Any]]:
        return [dict(row) for row in self._conn.execute("SELECT * FROM seasons WHERE status='completed' ORDER BY id DESC").fetchall()]

    def get_hall_of_fame(self, selected_season_id: Optional[int] = None, team_query: str = "", fighter_query: str = "") -> Dict[str, Any]:
        seasons = self.list_completed()
        if not seasons:
            return {
                "seasons": [],
                "selected_season": None,
                "leaderboard_rows": [],
                "fighter_rows": [],
                "available_teams": [],
                "available_fighters": [],
            }

        selected = None
        if selected_season_id:
            selected = next((season for season in seasons if season["id"] == selected_season_id), None)
        if selected is None:
            selected = seasons[0]

        team_needle = query_text(team_query)
        fighter_needle = query_text(fighter_query)

        leaderboard_rows_list = [
            dict(row)
            for row in self._conn.execute(
                """
                SELECT *
                FROM season_team_snapshots
                WHERE season_id=?
                ORDER BY rank IS NULL, rank, team_name
                """,
                (selected["id"],),
            ).fetchall()
        ]
        fighter_rows = [
            dict(row)
            for row in self._conn.execute(
                """
                SELECT *
                FROM season_fighter_snapshots
                WHERE season_id=?
                ORDER BY rank IS NULL, rank, name
                """,
                (selected["id"],),
            ).fetchall()
        ]
        cost_changes = [
            dict(row)
            for row in self._conn.execute(
                """
                SELECT *
                FROM season_cost_changes
                WHERE season_id=?
                ORDER BY ABS(new_cost - old_cost) DESC, fighter_name
                """,
                (selected["id"],),
            ).fetchall()
        ]

        available_teams = sorted(
            {row["team_name"] for row in leaderboard_rows_list if row.get("team_name")} |
            {row["player_name"] for row in leaderboard_rows_list if row.get("player_name")},
            key=query_text,
        )
        available_fighters = sorted({row["name"] for row in fighter_rows if row.get("name")}, key=query_text)

        if team_needle:
            leaderboard_rows_list = [
                row for row in leaderboard_rows_list
                if team_needle in query_text(f"{row.get('team_name', '')} {row.get('player_name', '')} {row.get('manager', '')}")
            ]
        if fighter_needle:
            fighter_rows = [row for row in fighter_rows if fighter_needle in query_text(row.get("name", ""))]

        top_team = next((row for row in leaderboard_rows_list if row.get("rank") == 1), None)
        top_fighter = fighter_rows[0] if fighter_rows else None
        biggest_riser = next((row for row in cost_changes if row["new_cost"] > row["old_cost"]), None)
        biggest_faller = next((row for row in cost_changes if row["new_cost"] < row["old_cost"]), None)

        for season in seasons:
            season_id = season["id"]
            if not season.get("final_leaderboard_json"):
                preview_rows = self._conn.execute(
                    """
                    SELECT team_name, player_name, rank, points
                    FROM season_team_snapshots
                    WHERE season_id=?
                    ORDER BY rank IS NULL, rank, team_name
                    LIMIT 3
                    """,
                    (season_id,),
                ).fetchall()
                season["leaderboard_preview"] = [dict(row) for row in preview_rows]
            else:
                season["leaderboard_preview"] = json.loads(season["final_leaderboard_json"])[:3]
            season["highlights"] = []
            if season.get("winner_team_name"):
                season["highlights"].append(f"Winner: {season['winner_team_name']}")
            season_top_fighter = self._conn.execute(
                """
                SELECT name, tier
                FROM season_fighter_snapshots
                WHERE season_id=?
                ORDER BY rank IS NULL, rank, name
                LIMIT 1
                """,
                (season_id,),
            ).fetchone()
            if season_top_fighter:
                season["highlights"].append(f"Top fighter: {season_top_fighter['name']} ({season_top_fighter['tier']})")

        return {
            "seasons": seasons,
            "selected_season": selected,
            "leaderboard_rows": leaderboard_rows_list,
            "fighter_rows": fighter_rows,
            "available_teams": available_teams,
            "available_fighters": available_fighters,
            "top_team": top_team,
            "top_fighter": top_fighter,
            "biggest_riser": biggest_riser,
            "biggest_faller": biggest_faller,
        }

    def get_cost_settings(self) -> Dict[str, Any]:
        settings = {r["key"]: r["value"] for r in self._conn.execute("SELECT key, value FROM settings").fetchall()}
        def int_setting(s, k, d=0):
            try:
                return int(float(s.get(k, d)))
            except Exception:
                return d
        return season_cost_settings_from_settings(settings, int_setting)

    def end_active_season(self) -> Dict[str, Any]:
        season = self.get_current_season()
        if not season or season["status"] != "active":
            raise ValidationError("There is no active season to end.")
        if season["locked"]:
            raise ValidationError(f"{season['name']} has already been ended.")

        season_id = season["id"]
        from app import team_rows, leaderboard_rows
        teams = [row for row in team_rows(self._conn)]
        fighters = [row for row in leaderboard_rows(self._conn)]
        winner = next((team for team in teams if team["rank"] == 1), None)
        cost_changes = calculate_season_cost_changes(fighters, teams, self.get_cost_settings())
        completed_at = now_iso()

        leaderboard_snapshot = [
            {
                "rank": team["rank"],
                "team_id": team["id"],
                "team_name": team["team_name"],
                "player_name": team.get("player_name"),
                "manager": team["manager"],
                "status": team["status"],
                "points": team["points"],
                "cost": team["cost"],
            }
            for team in teams
        ]

        self._conn.execute(
            """
            UPDATE seasons
            SET status='completed',
                locked=1,
                ended_at=?,
                winner_team_id=?,
                winner_team_name=?,
                winner_player_user_id=?,
                winner_player_name=?,
                final_leaderboard_json=?,
                completed_at=?
            WHERE id=?
            """,
            (
                completed_at,
                winner["id"] if winner else None,
                winner["team_name"] if winner else None,
                winner.get("player_user_id") if winner else None,
                winner.get("player_name") if winner else None,
                json.dumps(leaderboard_snapshot),
                completed_at,
                season_id,
            ),
        )
        self._conn.execute("DELETE FROM season_team_snapshots WHERE season_id=?", (season_id,))
        self._conn.execute("DELETE FROM season_fighter_snapshots WHERE season_id=?", (season_id,))
        self._conn.execute("DELETE FROM season_cost_changes WHERE season_id=?", (season_id,))

        for team in teams:
            snapshot = snapshot_team_row(team)
            self._conn.execute(
                """
                INSERT INTO season_team_snapshots(
                    season_id,team_id,rank,team_name,manager,player_user_id,player_name,status,points,cost,remaining,
                    member_count,image_path,image_credit,image_source_url,roster_json,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    season_id,
                    snapshot["team_id"],
                    snapshot["rank"],
                    snapshot["team_name"],
                    snapshot["manager"],
                    snapshot["player_user_id"],
                    snapshot["player_name"],
                    snapshot["status"],
                    snapshot["points"],
                    snapshot["cost"],
                    snapshot["remaining"],
                    snapshot["member_count"],
                    snapshot["image_path"],
                    snapshot["image_credit"],
                    snapshot["image_source_url"],
                    snapshot["roster_json"],
                    completed_at,
                ),
            )

        for fighter in fighters:
            self._conn.execute(
                """
                INSERT INTO season_fighter_snapshots(
                    season_id,fighter_id,rank,name,tier,current_cost,total_points,training,competitions,support,
                    gold_medals,silver_medals,bronze_medals,kills,deaths,sit_downs,yellow_cards,red_cards,
                    kd_ratio,fame_score,discipline_score,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    season_id,
                    fighter["id"],
                    fighter["rank"],
                    fighter["name"],
                    fighter.get("tier"),
                    fighter["current_cost"],
                    fighter["total_points"],
                    fighter["training"],
                    fighter["competitions"],
                    fighter["support"],
                    fighter["gold_medals"],
                    fighter["silver_medals"],
                    fighter["bronze_medals"],
                    fighter["kills"],
                    fighter["deaths"],
                    fighter["sit_downs"],
                    fighter["yellow_cards"],
                    fighter["red_cards"],
                    fighter["kd_ratio"],
                    fighter["fame_score"],
                    fighter["discipline_score"],
                    completed_at,
                ),
            )

        for change in cost_changes:
            self._conn.execute(
                """
                INSERT INTO season_cost_changes(
                    season_id,fighter_id,fighter_name,old_cost,new_cost,pick_count,team_count,pick_rate,target_pick_rate,
                    sensitivity,raw_adjustment,applied_adjustment,clamp_limit,round_unit,min_cost,max_cost,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    season_id,
                    change["fighter_id"],
                    change["fighter_name"],
                    change["old_cost"],
                    change["new_cost"],
                    change["pick_count"],
                    change["team_count"],
                    change["pick_rate"],
                    change["target_pick_rate"],
                    change["sensitivity"],
                    change["raw_adjustment"],
                    change["applied_adjustment"],
                    change["clamp_limit"],
                    change["round_unit"],
                    change["min_cost"],
                    change["max_cost"],
                    completed_at,
                ),
            )
            self._conn.execute("UPDATE fighters SET next_season_cost=? WHERE id=?", (change["new_cost"], change["fighter_id"]))
            log_audit(
                self._conn,
                "fighter_cost",
                change["fighter_id"],
                "season_cost_update",
                f"Updated next-season cost for {change['fighter_name']}.",
                before_state={
                    "season_id": season_id,
                    "fighter_name": change["fighter_name"],
                    "old_cost": change["old_cost"],
                    "pick_rate": change["pick_rate"],
                },
                after_state={
                    "season_id": season_id,
                    "fighter_name": change["fighter_name"],
                    "new_cost": change["new_cost"],
                    "pick_rate": change["pick_rate"],
                    "applied_adjustment": change["applied_adjustment"],
                },
            )

        log_audit(
            self._conn,
            "season",
            season_id,
            "complete",
            f"Ended {season['name']} and stored the final leaderboard.",
            before_state={"status": season["status"], "locked": season["locked"]},
            after_state={
                "status": "completed",
                "locked": 1,
                "winner_team_name": winner["team_name"] if winner else None,
                "cost_changes": len(cost_changes),
            },
            league_id=None,
        )
        create_notification(
            self._conn,
            f"{season['name']} ended",
            f"The final leaderboard has been stored. Winner: {winner['team_name'] if winner else 'No winner'}.",
            "success",
        )
        self._conn.commit()
        return {
            "season_id": season_id,
            "season_name": season["name"],
            "winner_team_name": winner["team_name"] if winner else None,
            "winner_player_name": winner.get("player_name") if winner else None,
            "cost_changes": cost_changes,
            "team_count": len(teams),
            "fighter_count": len(fighters),
        }


def snapshot_team_row(team) -> Dict[str, Any]:
    roster = []
    for fighter in team["fighters"]:
        roster.append(
            {
                "fighter_id": fighter["id"],
                "name": fighter["name"],
                "tier": fighter.get("tier"),
                "slot": fighter.get("slot"),
                "cost_used": fighter.get("cost_used"),
                "total_points": fighter.get("total_points"),
            }
        )
    return {
        "team_id": team["id"],
        "rank": team["rank"],
        "team_name": team["team_name"],
        "manager": team["manager"],
        "player_user_id": team["player_user_id"],
        "player_name": team.get("player_name"),
        "status": team["status"],
        "points": team["points"],
        "cost": team["cost"],
        "remaining": team["remaining"],
        "member_count": team["member_count"],
        "image_path": team.get("image_path"),
        "image_credit": team.get("image_credit"),
        "image_source_url": team.get("image_source_url"),
        "roster_json": json.dumps(roster),
    }


def current_season(conn):
    return SeasonLifecycleEngine(conn).get_current_season()


def ensure_active_season(conn):
    return SeasonLifecycleEngine(conn).ensure_active_season()


def season_lock_state(conn):
    return SeasonLifecycleEngine(conn).get_lock_state()


def require_active_season_editable(conn, action_label="This action"):
    return SeasonLifecycleEngine(conn).require_editable(action_label)


def completed_seasons(conn):
    return SeasonLifecycleEngine(conn).list_completed()


def hall_of_fame_data(conn, selected_season_id=None, team_query="", fighter_query=""):
    return SeasonLifecycleEngine(conn).get_hall_of_fame(selected_season_id, team_query, fighter_query)


def season_cost_settings(conn):
    return SeasonLifecycleEngine(conn).get_cost_settings()


def end_active_season(conn):
    return SeasonLifecycleEngine(conn).end_active_season()
