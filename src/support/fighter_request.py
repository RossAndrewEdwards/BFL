import datetime
import json
from typing import Dict, Any, Optional
from src.exceptions import ValidationError
from src.support.ops import log_audit


class FighterRequestEngine:
    """
    Unified domain manager for fighter profile proposal creation, request validation,
    and admin approval/denial flows.
    """
    def __init__(self, conn):
        self._conn = conn

    def validate_payload(self, payload: Dict[str, Any], *, require_name: bool) -> Dict[str, Any]:
        payload = dict(payload)
        name = (payload.get("name") or "").strip()
        if require_name and not name:
            raise ValidationError("Name is required.")
            
        for int_key in ("age", "joined_year"):
            val = payload.get(int_key)
            if val is not None and str(val).strip() != "":
                try:
                    parsed = int(str(val).strip())
                except ValueError as exc:
                    raise ValidationError(f"{int_key.replace('_', ' ').title()} must be a whole number.") from exc
                if parsed < 0:
                    raise ValidationError(f"{int_key.replace('_', ' ').title()} cannot be negative.")
                payload[int_key] = parsed
            else:
                payload[int_key] = None
                
        for float_key in ("height", "weight"):
            val = payload.get(float_key)
            if val is not None and str(val).strip() != "":
                try:
                    payload[float_key] = float(str(val).strip())
                except ValueError as exc:
                    raise ValidationError(f"{float_key.replace('_', ' ').title()} must be numeric.") from exc
            else:
                payload[float_key] = None
                
        return payload

    def create_proposal(self, user_id: int, league_id: int, request_type: str, payload: Dict[str, Any], fighter_id: Optional[int] = None) -> int:
        if request_type not in {"create", "edit"}:
            raise ValidationError("Invalid request type.")
            
        cleaned_payload = self.validate_payload(payload, require_name=(request_type == "create"))
        
        now = datetime.datetime.utcnow().isoformat()
        self._conn.execute(
            """
            INSERT INTO fighter_change_requests(league_id, fighter_id, requester_user_id, request_type, payload_json, status, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                league_id,
                fighter_id if request_type == "edit" else None,
                user_id,
                request_type,
                json.dumps(cleaned_payload),
                "pending",
                now,
                now,
            )
        )
        return self._conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def approve_proposal(self, request_id: int, reviewer_id: int, review_notes: Optional[str]) -> None:
        row = self._conn.execute(
            "SELECT * FROM fighter_change_requests WHERE id=?",
            (request_id,),
        ).fetchone()
        if not row:
            raise ValidationError("Fighter request not found.")
        if row["status"] != "pending":
            raise ValidationError("That request has already been reviewed.")
            
        payload = json.loads(row["payload_json"])
        now = datetime.datetime.utcnow().isoformat()
        review_notes = (review_notes or "").strip() or None
        
        if row["request_type"] == "edit":
            fighter = self._conn.execute(
                "SELECT * FROM fighters WHERE id=? AND league_id=?",
                (row["fighter_id"], row["league_id"]),
            ).fetchone()
            if not fighter:
                raise ValidationError("That fighter no longer exists in this league.")
                
            before = dict(fighter)
            self._conn.execute(
                """
                UPDATE fighters
                SET age=?, height=?, weight=?, nickname=?, fighting_style=?, preferred_role=?, role_or_weapon=?, known_for=?, why_buhurt=?, joined_year=?, bio=?, notes=?
                WHERE id=?
                """,
                (
                    payload.get("age"),
                    payload.get("height"),
                    payload.get("weight"),
                    payload.get("nickname", ""),
                    payload.get("fighting_style", ""),
                    payload.get("preferred_role", ""),
                    payload.get("role_or_weapon", ""),
                    payload.get("known_for", ""),
                    payload.get("why_buhurt", ""),
                    payload.get("joined_year"),
                    payload.get("bio", ""),
                    payload.get("notes", ""),
                    row["fighter_id"],
                ),
            )
            log_audit(
                self._conn,
                "fighter",
                row["fighter_id"],
                "update_from_request",
                f"Approved fighter edit request for {fighter['name']}.",
                before_state=before,
                after_state={"fighter_id": row["fighter_id"], "approved_request_id": request_id},
                league_id=row["league_id"],
            )
        else:
            self._conn.execute(
                """
                INSERT INTO fighters(
                    name, tier, age, height, weight, current_cost, notes, nickname, fighting_style,
                    preferred_role, role_or_weapon, known_for, why_buhurt, joined_year, reputation,
                    image_url, image_credit, image_source_url, bio, hero_quote, league_id
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    payload.get("name"),
                    "Tier 3",
                    payload.get("age"),
                    payload.get("height"),
                    payload.get("weight"),
                    50,
                    payload.get("notes", ""),
                    payload.get("nickname", ""),
                    payload.get("fighting_style", ""),
                    payload.get("preferred_role", ""),
                    payload.get("role_or_weapon", ""),
                    payload.get("known_for", ""),
                    payload.get("why_buhurt", ""),
                    payload.get("joined_year"),
                    "",
                    "",
                    "",
                    "",
                    payload.get("bio", ""),
                    "",
                    row["league_id"],
                ),
            )
            fighter_id = self._conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            self._conn.execute(
                "INSERT INTO baseline_stats(fighter_id, training, support) VALUES(?,?,?)",
                (fighter_id, 0, 0),
            )
            log_audit(
                self._conn,
                "fighter",
                fighter_id,
                "create_from_request",
                f"Approved new fighter request for {payload.get('name')}.",
                after_state={"fighter_id": fighter_id, "approved_request_id": request_id},
                league_id=row["league_id"],
            )
            
        self._conn.execute(
            """
            UPDATE fighter_change_requests
            SET status='approved', review_notes=?, reviewed_by_user_id=?, reviewed_at=?, updated_at=?
            WHERE id=?
            """,
            (review_notes, reviewer_id, now, now, request_id),
        )

    def deny_proposal(self, request_id: int, reviewer_id: int, review_notes: Optional[str]) -> None:
        row = self._conn.execute(
            "SELECT * FROM fighter_change_requests WHERE id=?",
            (request_id,),
        ).fetchone()
        if not row:
            raise ValidationError("Fighter request not found.")
        if row["status"] != "pending":
            raise ValidationError("That request has already been reviewed.")
            
        payload = json.loads(row["payload_json"])
        now = datetime.datetime.utcnow().isoformat()
        review_notes = (review_notes or "").strip() or None
        
        self._conn.execute(
            """
            UPDATE fighter_change_requests
            SET status='denied', review_notes=?, reviewed_by_user_id=?, reviewed_at=?, updated_at=?
            WHERE id=?
            """,
            (review_notes, reviewer_id, now, now, request_id),
        )
        
        log_audit(
            self._conn,
            "fighter_change_request",
            request_id,
            "deny",
            f"Denied fighter request: {row['request_type']} for {payload.get('name') or 'Fighter'}.",
            after_state={"request_id": request_id, "status": "denied"},
            league_id=row["league_id"],
        )
