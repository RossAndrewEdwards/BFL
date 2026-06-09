import datetime
from typing import List, Dict, Any, Tuple, Optional
from src.exceptions import ValidationError
from src.support.ops import log_audit
from src.support.season import require_active_season_editable


class TrainingHonoursEngine:
    """
    Unified domain coordinator for training group creation, membership management,
    attendance/workout marking, and record logging for fighter honors and awards.
    """
    def __init__(self, conn):
        self._conn = conn

    def validate_group_fighter_ids(self, league_id: int, fighter_ids: List[Any]) -> List[int]:
        cleaned = []
        for raw in fighter_ids:
            raw_value = str(raw or "").strip()
            if not raw_value:
                continue
            try:
                cleaned.append(int(raw_value))
            except ValueError as exc:
                raise ValidationError("Choose valid fighters for this training group.") from exc
        if not cleaned:
            return []
        rows = self._conn.execute(
            f"""
            SELECT id
            FROM fighters
            WHERE league_id=? AND id IN ({",".join("?" for _ in cleaned)})
            """,
            (league_id, *cleaned),
        ).fetchall()
        valid_ids = {row["id"] for row in rows}
        if len(valid_ids) != len(set(cleaned)):
            raise ValidationError("Training groups can only contain fighters from the selected league.")
        return cleaned

    def create_group(self, league_id: int, name: str, notes: str, fighter_ids: List[Any]) -> int:
        name = (name or "").strip()
        if not name:
            raise ValidationError("Training group name is required.")
        
        cleaned_ids = self.validate_group_fighter_ids(league_id, fighter_ids)
        now = datetime.datetime.utcnow().isoformat()
        
        next_sort = self._conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM training_groups WHERE league_id=?",
            (league_id,),
        ).fetchone()[0]
        
        self._conn.execute(
            """
            INSERT INTO training_groups(league_id, name, notes, sort_order, created_at, updated_at)
            VALUES(?,?,?,?,?,?)
            """,
            (league_id, name, notes or "", next_sort, now, now),
        )
        group_id = self._conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        if cleaned_ids:
            self._conn.executemany(
                """
                INSERT INTO training_group_members(training_group_id, fighter_id, position, created_at)
                VALUES(?,?,?,?)
                """,
                [(group_id, fighter_id, index, now) for index, fighter_id in enumerate(cleaned_ids, start=1)],
            )
            
        log_audit(
            self._conn,
            "training_group",
            group_id,
            "create",
            f"Created training group {name}.",
            after_state={"fighter_ids": cleaned_ids, "league_id": league_id},
            league_id=league_id,
        )
        return group_id

    def update_group_members(self, group_id: int, fighter_ids: List[Any]) -> None:
        group = self._conn.execute(
            "SELECT * FROM training_groups WHERE id=?",
            (group_id,),
        ).fetchone()
        if not group:
            raise ValidationError("Training group not found.")
            
        cleaned_ids = self.validate_group_fighter_ids(group["league_id"], fighter_ids)
        now = datetime.datetime.utcnow().isoformat()
        
        self._conn.execute("DELETE FROM training_group_members WHERE training_group_id=?", (group_id,))
        if cleaned_ids:
            self._conn.executemany(
                """
                INSERT INTO training_group_members(training_group_id, fighter_id, position, created_at)
                VALUES(?,?,?,?)
                """,
                [(group_id, fighter_id, index, now) for index, fighter_id in enumerate(cleaned_ids, start=1)],
            )
            
        self._conn.execute("UPDATE training_groups SET updated_at=? WHERE id=?", (now, group_id))
        log_audit(
            self._conn,
            "training_group",
            group_id,
            "update_members",
            f"Updated members for training group {group['name']}.",
            after_state={"fighter_ids": cleaned_ids},
            league_id=group["league_id"],
        )

    def delete_group(self, group_id: int) -> None:
        group = self._conn.execute(
            "SELECT * FROM training_groups WHERE id=?",
            (group_id,),
        ).fetchone()
        if not group:
            raise ValidationError("Training group not found.")
            
        self._conn.execute("DELETE FROM training_groups WHERE id=?", (group_id,))
        log_audit(
            self._conn,
            "training_group",
            group_id,
            "delete",
            f"Deleted training group {group['name']}.",
            before_state={"name": group["name"]},
            league_id=group["league_id"],
        )

    def mark_attendance(self, group_id: int, payload: Dict[str, Any]) -> int:
        group = self._conn.execute(
            "SELECT * FROM training_groups WHERE id=?",
            (group_id,),
        ).fetchone()
        if not group:
            raise ValidationError("Training group not found.")
            
        require_active_season_editable(self._conn, "Training and support changes")
        
        fighters = self._conn.execute(
            """
            SELECT f.id, f.name, f.league_id
            FROM training_group_members tgm
            JOIN fighters f ON f.id = tgm.fighter_id
            WHERE tgm.training_group_id=?
            ORDER BY tgm.position, tgm.id
            """,
            (group_id,),
        ).fetchall()
        
        if not fighters:
            raise ValidationError("Add fighters to this group before marking attendance.")
            
        for fighter in fighters:
            self.mark_fighter_attendance(
                fighter["id"],
                payload,
                source=f"training_workspace_group:{group['name']}",
                skip_season_check=True,
            )
            
        log_audit(
            self._conn,
            "training_group",
            group_id,
            "mark_attendance",
            f"Marked {payload['score_type']} for training group {group['name']}.",
            after_state={
                "score_type": payload["score_type"],
                "score_units": payload["score_units"],
                "attendance_date": payload["attendance_date"],
                "fighter_count": len(fighters),
            },
            league_id=group["league_id"],
        )
        return len(fighters)

    def mark_fighter_attendance(self, fighter_id: int, payload: Dict[str, Any], source: str, skip_season_check: bool = False) -> Tuple[int, int]:
        if not skip_season_check:
            require_active_season_editable(self._conn, "Training and support changes")
            
        fighter = self._conn.execute(
            "SELECT id, name, league_id FROM fighters WHERE id=?",
            (fighter_id,),
        ).fetchone()
        if not fighter:
            raise ValidationError("Selected fighter does not exist.")
            
        baseline = self._conn.execute(
            "SELECT training, support FROM baseline_stats WHERE fighter_id=?",
            (fighter_id,),
        ).fetchone()
        
        current_training = int((baseline["training"] if baseline else 0) or 0)
        current_support = int((baseline["support"] if baseline else 0) or 0)
        increment = int(payload["score_units"] or 0)
        next_training = current_training + (increment if payload["score_type"] == "training" else 0)
        next_support = current_support + (increment if payload["score_type"] == "support" else 0)
        
        self._conn.execute(
            """
            INSERT INTO baseline_stats(fighter_id, training, support)
            VALUES(?,?,?)
            ON CONFLICT(fighter_id) DO UPDATE SET
                training=excluded.training,
                support=excluded.support
            """,
            (fighter_id, next_training, next_support),
        )
        
        log_audit(
            self._conn,
            "fighter",
            fighter_id,
            "stat_adjust",
            f"Added {payload['score_units']} {payload['score_type']} for {fighter['name']}.",
            before_state={"training": current_training, "support": current_support},
            after_state={
                "training": next_training,
                "support": next_support,
                "source": source,
                "note": payload["note"],
                "attendance_date": payload["attendance_date"],
            },
            league_id=fighter["league_id"],
        )
        return next_training, next_support

    def record_honour(
        self,
        league_id: int,
        fighter_id: int,
        honour_type: str,
        units: int,
        title: str,
        notes: str,
        awarded_on: str,
    ) -> int:
        if honour_type not in {"special_awards", "gold_medals", "silver_medals", "bronze_medals"}:
            raise ValidationError("Choose a valid honour type.")
            
        try:
            datetime.datetime.strptime(awarded_on, "%Y-%m-%d")
        except ValueError as exc:
            raise ValidationError("Awarded on date must be in YYYY-MM-DD format.") from exc
            
        fighter = self._conn.execute(
            "SELECT id, name, league_id FROM fighters WHERE id=? AND league_id=?",
            (fighter_id, league_id),
        ).fetchone()
        if not fighter:
            raise ValidationError("Choose a fighter from this league.")
            
        now = datetime.datetime.utcnow().isoformat()
        self._conn.execute(
            """
            INSERT INTO fighter_honours(league_id, fighter_id, honour_type, units, title, notes, awarded_on, created_at)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (league_id, fighter_id, honour_type, units, title or "", notes or "", awarded_on, now),
        )
        honour_id = self._conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        
        log_audit(
            self._conn,
            "fighter_honour",
            honour_id,
            "create",
            f"Recorded {units} {honour_type.replace('_', ' ')} for {fighter['name']}.",
            after_state={
                "fighter_id": fighter_id,
                "honour_type": honour_type,
                "units": units,
                "title": title,
                "awarded_on": awarded_on,
            },
            league_id=league_id,
        )
        return honour_id
