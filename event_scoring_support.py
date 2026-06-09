import datetime
from typing import List, Dict, Any, Tuple
from exceptions import ValidationError
from ops_support import log_audit, event_result_audit_state
from season_support import require_active_season_editable


class EventScoringCoordinator:
    """
    Unified domain coordinator for event result creation, group/match scoring workspace,
    statistics updates, and validation policies for score entry.
    """
    def __init__(self, conn):
        self._conn = conn

    def _now_iso(self) -> str:
        return datetime.datetime.utcnow().replace(microsecond=0).isoformat()

    def _get_banner(self, banner_id: int) -> Dict[str, Any]:
        banner = self._conn.execute(
            "SELECT * FROM event_banners WHERE id=?",
            (banner_id,),
        ).fetchone()
        if not banner:
            raise ValidationError("Choose a valid scheduled event.")
        return dict(banner)

    def _get_fighter(self, fighter_id: int, league_id: int) -> Dict[str, Any]:
        fighter = self._conn.execute(
            "SELECT id, name, league_id FROM fighters WHERE id=? AND league_id=?",
            (fighter_id, league_id),
        ).fetchone()
        if not fighter:
            raise ValidationError("Select a fighter from your league before saving results.")
        return dict(fighter)

    def add_fighters_to_group(self, banner_id: int, group_name: str, fighter_ids: List[Any]) -> int:
        group_name = (group_name or "").strip()
        if not group_name:
            raise ValidationError("Group or match name is required.")
        if not fighter_ids:
            raise ValidationError("Choose at least one fighter to add to the group.")

        require_active_season_editable(self._conn, "Event result changes")
        banner = self._get_banner(banner_id)
        
        created_count = 0
        for raw_id in fighter_ids:
            try:
                fighter_id = int(raw_id)
            except ValueError as exc:
                raise ValidationError("Choose valid fighters for the group.") from exc
                
            fighter = self._get_fighter(fighter_id, banner["league_id"])
            
            duplicate = self._conn.execute(
                """
                SELECT 1
                FROM event_results
                WHERE scheduled_event_id=? AND fighter_id=? AND league_id=?
                """,
                (banner_id, fighter_id, banner["league_id"]),
            ).fetchone()
            if duplicate:
                continue
                
            self._conn.execute(
                """
                INSERT INTO event_results(
                    scheduled_event_id, event_date, event_name, fighter_id, league_id, group_name, entry_status, updated_at,
                    rounds_fought, special_awards, gold_medals, silver_medals, bronze_medals, kills, assists, deaths, sit_downs, yellow_cards, red_cards
                ) VALUES(?,?,?,?,?,?,?,?,0,0,0,0,0,0,0,0,0,0,0)
                """,
                (
                    banner_id,
                    banner["event_date"],
                    banner["event_name"],
                    fighter_id,
                    banner["league_id"],
                    group_name,
                    "draft",
                    self._now_iso(),
                ),
            )
            created_id = self._conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            
            inserted = event_result_audit_state(self._conn, created_id)
            log_audit(
                self._conn,
                "event_result",
                created_id,
                "create",
                f"Added {fighter['name']} to scoring group {group_name} for {banner['event_name']}.",
                after_state=inserted,
                rollback_type="event_create",
            )
            created_count += 1
            
        return created_count

    def save_group_scores(self, banner_id: int, group_name: str, score_payloads: Dict[int, Dict[str, int]], entry_status: str) -> None:
        group_name = (group_name or "").strip()
        if not group_name:
            raise ValidationError("Group or match name is required.")
            
        require_active_season_editable(self._conn, "Event result changes")
        banner = self._get_banner(banner_id)
        
        for result_id, stats in score_payloads.items():
            row = self._conn.execute(
                """
                SELECT er.*, f.name AS fighter_name
                FROM event_results er
                JOIN fighters f ON f.id = er.fighter_id
                WHERE er.id=? AND er.scheduled_event_id=? AND COALESCE(er.group_name, '')=?
                """,
                (result_id, banner_id, group_name),
            ).fetchone()
            if not row:
                raise ValidationError("That group does not have any fighters yet.")
                
            before = event_result_audit_state(self._conn, result_id)
            
            for field, val in stats.items():
                if val < 0:
                    raise ValidationError(f"{row['fighter_name']} cannot have negative values.")
                    
            self._conn.execute(
                """
                UPDATE event_results
                SET entry_status=?,
                    updated_at=?,
                    rounds_fought=?,
                    special_awards=?,
                    gold_medals=?,
                    silver_medals=?,
                    bronze_medals=?,
                    kills=?,
                    assists=?,
                    deaths=?,
                    sit_downs=?,
                    yellow_cards=?,
                    red_cards=?
                WHERE id=?
                """,
                (
                    entry_status,
                    self._now_iso(),
                    stats["rounds_fought"],
                    stats["special_awards"],
                    stats["gold_medals"],
                    stats["silver_medals"],
                    stats["bronze_medals"],
                    stats["kills"],
                    stats["assists"],
                    stats["deaths"],
                    stats["sit_downs"],
                    stats["yellow_cards"],
                    stats["red_cards"],
                    result_id,
                ),
            )
            
            after = event_result_audit_state(self._conn, result_id)
            log_audit(
                self._conn,
                "event_result",
                result_id,
                "update",
                f"Updated grouped result for {banner['event_name']} and {row['fighter_name']}.",
                before_state=before,
                after_state=after,
            )

    def create_manual_result(self, banner_id: int, fighter_id: int, stats: Dict[str, int], group_name: str, entry_status: str) -> int:
        require_active_season_editable(self._conn, "Event result changes")
        banner = self._get_banner(banner_id)
        fighter = self._get_fighter(fighter_id, banner["league_id"])
        
        duplicate = self._conn.execute(
            """
            SELECT 1
            FROM event_results
            WHERE scheduled_event_id=? AND fighter_id=? AND league_id=?
            """,
            (banner_id, fighter_id, banner["league_id"]),
        ).fetchone()
        if duplicate:
            raise ValidationError("That fighter already has results recorded for the selected event.")
            
        for field, val in stats.items():
            if val < 0:
                raise ValidationError("Event statistics cannot be negative.")
                
        self._conn.execute(
            """
            INSERT INTO event_results(
                scheduled_event_id, event_date, event_name, fighter_id, league_id, group_name, entry_status, updated_at,
                rounds_fought, special_awards, gold_medals, silver_medals, bronze_medals, kills, assists, deaths, sit_downs, yellow_cards, red_cards
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                banner_id,
                banner["event_date"],
                banner["event_name"],
                fighter_id,
                banner["league_id"],
                group_name or None,
                entry_status,
                self._now_iso(),
                stats["rounds_fought"],
                stats["special_awards"],
                stats["gold_medals"],
                stats["silver_medals"],
                stats["bronze_medals"],
                stats["kills"],
                stats["assists"],
                stats["deaths"],
                stats["sit_downs"],
                stats["yellow_cards"],
                stats["red_cards"],
            ),
        )
        event_id = self._conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        inserted = event_result_audit_state(self._conn, event_id)
        log_audit(
            self._conn,
            "event_result",
            event_id,
            "create",
            f"Added event result for {banner['event_name']} and {fighter['name']}.",
            after_state=inserted,
            rollback_type="event_create",
        )
        return event_id

    def update_event_result(self, event_id: int, banner_id: int, fighter_id: int, stats: Dict[str, int], group_name: str, entry_status: str) -> None:
        require_active_season_editable(self._conn, "Event result changes")
        banner = self._get_banner(banner_id)
        fighter = self._get_fighter(fighter_id, banner["league_id"])
        
        duplicate = self._conn.execute(
            """
            SELECT 1
            FROM event_results
            WHERE scheduled_event_id=? AND fighter_id=? AND id<>? AND league_id=?
            """,
            (banner_id, fighter_id, event_id, banner["league_id"]),
        ).fetchone()
        if duplicate:
            raise ValidationError("That fighter already has results recorded for the selected event.")
            
        for field, val in stats.items():
            if val < 0:
                raise ValidationError("Event statistics cannot be negative.")
                
        before = event_result_audit_state(self._conn, event_id)
        
        self._conn.execute(
            """
            UPDATE event_results
            SET scheduled_event_id=?,
                event_date=?,
                event_name=?,
                fighter_id=?,
                group_name=?,
                entry_status=?,
                updated_at=?,
                rounds_fought=?,
                special_awards=?,
                gold_medals=?,
                silver_medals=?,
                bronze_medals=?,
                kills=?,
                assists=?,
                deaths=?,
                sit_downs=?,
                yellow_cards=?,
                red_cards=?
            WHERE id=?
            """,
            (
                banner_id,
                banner["event_date"],
                banner["event_name"],
                fighter_id,
                group_name or None,
                entry_status,
                self._now_iso(),
                stats["rounds_fought"],
                stats["special_awards"],
                stats["gold_medals"],
                stats["silver_medals"],
                stats["bronze_medals"],
                stats["kills"],
                stats["assists"],
                stats["deaths"],
                stats["sit_downs"],
                stats["yellow_cards"],
                stats["red_cards"],
                event_id,
            ),
        )
        
        after = event_result_audit_state(self._conn, event_id)
        log_audit(
            self._conn,
            "event_result",
            event_id,
            "update",
            f"Updated event result for {banner['event_name']} and {fighter['name']}.",
            before_state=before,
            after_state=after,
        )
