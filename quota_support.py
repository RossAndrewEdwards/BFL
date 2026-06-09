from typing import Optional, Dict, Any
from exceptions import QuotaExceededError


class LeagueQuotaManager:
    """
    Unified domain manager for league quota verification (player capacity and team capacity).
    """
    def __init__(self, conn):
        self._conn = conn

    def get_summary(self, league_id: Any) -> Optional[Dict[str, Any]]:
        if not league_id:
            return None
        league = self._conn.execute(
            "SELECT id, name, max_players, max_teams FROM leagues WHERE id=?",
            (league_id,),
        ).fetchone()
        if not league:
            return None
        players_used = self._conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM league_memberships
            WHERE league_id=?
              AND status='active'
              AND (role='player' OR manager_limit > 0)
            """,
            (league_id,),
        ).fetchone()["c"]
        teams_used = self._conn.execute(
            "SELECT COUNT(*) AS c FROM fantasy_teams WHERE league_id=?",
            (league_id,),
        ).fetchone()["c"]

        def remaining(maximum, used):
            if maximum is None:
                return None
            return max(0, int(maximum) - int(used))

        return {
            "league_id": league["id"],
            "league_name": league["name"],
            "max_players": league["max_players"],
            "max_teams": league["max_teams"],
            "players_used": players_used,
            "teams_used": teams_used,
            "players_remaining": remaining(league["max_players"], players_used),
            "teams_remaining": remaining(league["max_teams"], teams_used),
        }

    def check_player_capacity(self, league_id: Any) -> Optional[Dict[str, Any]]:
        summary = self.get_summary(league_id)
        if summary and summary["max_players"] is not None and summary["players_used"] >= summary["max_players"]:
            raise QuotaExceededError(
                f"Player quota reached for {summary['league_name']}. "
                f"{summary['players_used']} of {summary['max_players']} player slots are already in use."
            )
        return summary

    def check_team_capacity(self, league_id: Any) -> Optional[Dict[str, Any]]:
        summary = self.get_summary(league_id)
        if summary and summary["max_teams"] is not None and summary["teams_used"] >= summary["max_teams"]:
            raise QuotaExceededError(
                f"Team quota reached for {summary['league_name']}. "
                f"{summary['teams_used']} of {summary['max_teams']} team slots are already in use."
            )
        return summary


def league_quota_summary(conn, league_id):
    return LeagueQuotaManager(conn).get_summary(league_id)


def require_player_capacity(conn, league_id):
    return LeagueQuotaManager(conn).check_player_capacity(league_id)


def require_team_capacity(conn, league_id):
    return LeagueQuotaManager(conn).check_team_capacity(league_id)
