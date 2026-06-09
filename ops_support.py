from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Generator
from contextlib import contextmanager
from abc import ABC, abstractmethod
import sqlite3
import json

_AUDIT_LEAGUE_UNSET = object()


def now_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat()


def get_current_user_id():
    try:
        from flask import session
        return session.get("user_id")
    except RuntimeError:
        return None


class SessionProvider(ABC):
    @abstractmethod
    def get_current_user_id(self) -> Optional[int]:
        pass

    @abstractmethod
    def get_active_league_id(self, conn: sqlite3.Connection) -> Optional[int]:
        pass


class FlaskSessionProvider(SessionProvider):
    def get_current_user_id(self) -> Optional[int]:
        return get_current_user_id()

    def get_active_league_id(self, conn: sqlite3.Connection) -> Optional[int]:
        try:
            from flask import session
            if session.get("active_league_id"):
                return session["active_league_id"]
        except RuntimeError:
            pass
        row = conn.execute("SELECT id FROM leagues WHERE slug='invicta'").fetchone()
        return row["id"] if row else None


class ManualSessionProvider(SessionProvider):
    def __init__(self, user_id: Optional[int] = None, league_id: Optional[int] = None):
        self.user_id = user_id
        self.league_id = league_id

    def get_current_user_id(self) -> Optional[int]:
        return self.user_id

    def get_active_league_id(self, conn: sqlite3.Connection) -> Optional[int]:
        if self.league_id is not None:
            return self.league_id
        row = conn.execute("SELECT id FROM leagues WHERE slug='invicta'").fetchone()
        return row["id"] if row else None


class AuditContext:
    def __init__(self, entity_type: str, action: str, message: str, entity_id: Optional[int] = None):
        self.entity_type = entity_type
        self.action = action
        self.message = message
        self.entity_id = entity_id


class JournalNamespace:
    def __init__(self, conn: sqlite3.Connection, session_provider: SessionProvider):
        self._conn = conn
        self._session_provider = session_provider

    @contextmanager
    def capture(
        self,
        entity_type: str,
        action: str,
        message: str,
        entity_id: Optional[int] = None,
        league_id: Any = _AUDIT_LEAGUE_UNSET,
        rollback_type: Optional[str] = None
    ) -> Generator[AuditContext, None, None]:
        ctx = AuditContext(entity_type, action, message, entity_id)
        
        before_state = None
        if entity_id is not None:
            before_state = self._fetch_entity_state(entity_type, entity_id)

        yield ctx
        
        resolved_entity_id = ctx.entity_id or entity_id
        after_state = None
        if resolved_entity_id is not None:
            after_state = self._fetch_entity_state(entity_type, resolved_entity_id)

        self.log(
            entity_type=ctx.entity_type,
            entity_id=resolved_entity_id,
            action=ctx.action,
            message=ctx.message,
            before_state=before_state,
            after_state=after_state,
            rollback_type=rollback_type,
            league_id=league_id
        )

    def _fetch_entity_state(self, entity_type: str, entity_id: int) -> Optional[Dict[str, Any]]:
        if entity_type == "team":
            return team_state(self._conn, entity_id)
        elif entity_type == "event_result":
            return event_result_audit_state(self._conn, entity_id) or event_state(self._conn, entity_id)
        elif entity_type == "fighter":
            row = self._conn.execute("SELECT id, name FROM fighters WHERE id=?", (entity_id,)).fetchone()
            return dict(row) if row else None
        elif entity_type == "user":
            row = self._conn.execute("SELECT id, username, display_name, role, league_id FROM users WHERE id=?", (entity_id,)).fetchone()
            return dict(row) if row else None
        return None

    def log(
        self,
        entity_type: str,
        entity_id: Optional[int],
        action: str,
        message: str,
        before_state: Optional[Any] = None,
        after_state: Optional[Any] = None,
        rollback_type: Optional[str] = None,
        league_id: Any = _AUDIT_LEAGUE_UNSET,
        actor_user_id: Optional[int] = None
    ) -> None:
        resolved_league_id = self._session_provider.get_active_league_id(self._conn) if league_id is _AUDIT_LEAGUE_UNSET else league_id
        resolved_actor_user_id = actor_user_id if actor_user_id is not None else self._session_provider.get_current_user_id()
        
        self._conn.execute(
            """
            INSERT INTO audit_logs(actor_user_id,league_id,created_at,entity_type,entity_id,action,message,before_state,after_state,rollback_type)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                resolved_actor_user_id,
                resolved_league_id,
                now_iso(),
                entity_type,
                entity_id,
                action,
                message,
                json.dumps(before_state) if before_state is not None else None,
                json.dumps(after_state) if after_state is not None else None,
                rollback_type,
            ),
        )

    def rollback(self, audit_id: int, actor_user_id: Optional[int] = None) -> None:
        from exceptions import ValidationError
        row = self._conn.execute("SELECT * FROM audit_logs WHERE id=?", (audit_id,)).fetchone()
        if not row:
            raise ValidationError("Audit log entry not found.")
        if not row["rollback_type"]:
            raise ValidationError("That audit entry cannot be rolled back.")
            
        before_state = json.loads(row["before_state"]) if row["before_state"] else None
        after_state = json.loads(row["after_state"]) if row["after_state"] else None
        rollback_type = row["rollback_type"]
        entity_id = row["entity_id"]
        entity_type = row["entity_type"]
        league_id = row["league_id"]
        
        if rollback_type == "event_create":
            self._conn.execute("DELETE FROM event_results WHERE id=?", (entity_id,))
        elif rollback_type == "attendance_create":
            self._conn.execute("DELETE FROM attendance_scores WHERE id=?", (entity_id,))
        elif rollback_type == "event_delete" and before_state:
            l_id = before_state.get("league_id") or league_id or self._session_provider.get_active_league_id(self._conn)
            self._conn.execute(
                """
                INSERT INTO event_results(id,scheduled_event_id,event_date,event_name,fighter_id,league_id,rounds_fought,special_awards,gold_medals,silver_medals,bronze_medals,kills,assists,deaths,sit_downs,yellow_cards,red_cards)
                VALUES(:id,:scheduled_event_id,:event_date,:event_name,:fighter_id,:league_id,:rounds_fought,:special_awards,:gold_medals,:silver_medals,:bronze_medals,:kills,:assists,:deaths,:sit_downs,:yellow_cards,:red_cards)
                """,
                {**before_state, "league_id": l_id},
            )
        elif rollback_type == "team_update" and before_state:
            self._conn.execute(
                "UPDATE fantasy_teams SET team_name=?, manager=?, player_user_id=? WHERE id=?",
                (
                    before_state["team"]["team_name"],
                    before_state["team"]["manager"],
                    before_state["team"].get("player_user_id"),
                    before_state["team"]["id"],
                ),
            )
            self._conn.execute("DELETE FROM fantasy_team_fighters WHERE team_id=?", (before_state["team"]["id"],))
            for fighter in before_state["fighters"]:
                self._conn.execute(
                    "INSERT INTO fantasy_team_fighters(team_id,fighter_id,slot) VALUES(?,?,?)",
                    (before_state["team"]["id"], fighter["fighter_id"], fighter["slot"]),
                )
        else:
            raise ValidationError("Rollback is not available for that entry.")

        # Clear the rollback_type on the original audit record to prevent double-rollback
        self._conn.execute("UPDATE audit_logs SET rollback_type=NULL WHERE id=?", (audit_id,))
        
        # Log a new audit entry to record the rollback action
        self.log(
            entity_type=entity_type,
            entity_id=entity_id,
            action="rollback",
            message=f"Rolled back audit entry #{audit_id}.",
            before_state=after_state,
            after_state=before_state,
            league_id=league_id,
            actor_user_id=actor_user_id
        )

    def query(self, limit: int = 100) -> List[Dict[str, Any]]:
        return [dict(row) for row in self._conn.execute(
            """
            SELECT al.*, u.display_name AS actor_name, l.name AS league_name
            FROM audit_logs al
            LEFT JOIN users u ON u.id = al.actor_user_id
            LEFT JOIN leagues l ON l.id = al.league_id
            ORDER BY al.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()]


class AlertsNamespace:
    def __init__(self, conn: sqlite3.Connection, session_provider: SessionProvider):
        self._conn = conn
        self._session_provider = session_provider

    def publish(
        self,
        title: str,
        body: str,
        kind: str = "update",
        expires_at: Optional[str] = None,
        league_id: Any = _AUDIT_LEAGUE_UNSET
    ) -> int:
        resolved_league_id = self._session_provider.get_active_league_id(self._conn) if league_id is _AUDIT_LEAGUE_UNSET else league_id
        cursor = self._conn.execute(
            "INSERT INTO notifications(league_id,title,body,kind,created_at,expires_at,is_active) VALUES(?,?,?,?,?,?,1)",
            (resolved_league_id, title, body, kind, now_iso(), expires_at),
        )
        notification_id = cursor.lastrowid
        # Log audit entry
        self._engine.journal.log(
            entity_type="notification",
            entity_id=notification_id,
            action="create",
            message=f"Notification created: {title}",
            league_id=resolved_league_id
        )
        return notification_id

    def toggle(self, notification_id: int) -> bool:
        from exceptions import ValidationError
        row = self._conn.execute("SELECT is_active, title, league_id FROM notifications WHERE id=?", (notification_id,)).fetchone()
        if not row:
            raise ValidationError("Notification not found.")
        new_value = 0 if row["is_active"] else 1
        self._conn.execute("UPDATE notifications SET is_active=? WHERE id=?", (new_value, notification_id))
        # Log audit entry
        self._engine.journal.log(
            entity_type="notification",
            entity_id=notification_id,
            action="toggle",
            message=f"Notification {'activated' if new_value else 'paused'}: {row['title']}",
            league_id=row["league_id"]
        )
        return bool(new_value)

    def list_active(self, limit: int = 5) -> List[Dict[str, Any]]:
        return [dict(row) for row in self._conn.execute(
            """
            SELECT *
            FROM notifications
            WHERE is_active=1
              AND (expires_at IS NULL OR expires_at >= ?)
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (now_iso(), limit),
        ).fetchall()]


class TokensNamespace:
    def __init__(self, conn: sqlite3.Connection, session_provider: SessionProvider):
        self._conn = conn
        self._session_provider = session_provider

    def get_or_create_share(self, team_id: int) -> str:
        import secrets
        row = self._conn.execute("SELECT token FROM team_share_links WHERE team_id=?", (team_id,)).fetchone()
        if row:
            return row["token"]
        token = secrets.token_urlsafe(16)
        self._conn.execute(
            "INSERT INTO team_share_links(team_id,token,created_at) VALUES(?,?,?)",
            (team_id, token, now_iso()),
        )
        return token

    def resolve_share(self, token: str) -> int:
        from exceptions import ValidationError
        row = self._conn.execute("SELECT team_id FROM team_share_links WHERE token=?", (token,)).fetchone()
        if not row:
            raise ValidationError("Invalid share token.")
        return row["team_id"]

    def issue_claim(self, user_id: int) -> Dict[str, Any]:
        import secrets
        self._conn.execute("UPDATE claim_tokens SET used_at=? WHERE user_id=? AND used_at IS NULL", (now_iso(), user_id))
        token = secrets.token_urlsafe(24)
        code = secrets.token_hex(4).upper()
        utcnow = datetime.utcnow().replace(microsecond=0)
        expires_at = utcnow + timedelta(hours=72)
        
        user = self._conn.execute("SELECT league_id FROM users WHERE id=?", (user_id,)).fetchone()
        membership = self._conn.execute(
            """
            SELECT league_id
            FROM league_memberships
            WHERE user_id=?
            ORDER BY
                CASE
                    WHEN status='active' AND league_id=? THEN 0
                    WHEN status='active' THEN 1
                    WHEN status='invited' THEN 2
                    ELSE 3
                END,
                league_id,
                id
            LIMIT 1
            """,
            (user_id, user["league_id"] if user else None),
        ).fetchone()
        league_id = membership["league_id"] if membership else (user["league_id"] if user else self._session_provider.get_active_league_id(self._conn))
        
        self._conn.execute(
            "INSERT INTO claim_tokens(user_id,league_id,token,code,created_at,expires_at,used_at) VALUES(?,?,?,?,?,?,NULL)",
            (user_id, league_id, token, code, utcnow.isoformat(), expires_at.isoformat()),
        )
        return {"token": token, "code": code, "expires_at": expires_at.isoformat()}

    def active_for_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            """
            SELECT *
            FROM claim_tokens
            WHERE user_id=? AND used_at IS NULL AND expires_at >= ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id, now_iso()),
        ).fetchone()
        return dict(row) if row else None

    def resolve_claim_code(self, code: str) -> Dict[str, Any]:
        from exceptions import ValidationError
        row = self._conn.execute(
            """
            SELECT *
            FROM claim_tokens
            WHERE code=? AND used_at IS NULL AND expires_at >= ?
            """,
            (code.upper(), now_iso()),
        ).fetchone()
        if not row:
            raise ValidationError("Invalid or expired claim code.")
        return dict(row)

    def execute_claim(self, token: str, display_name: str, password_raw: str) -> int:
        from exceptions import ValidationError
        row = self._conn.execute(
            """
            SELECT *
            FROM claim_tokens
            WHERE token=? AND used_at IS NULL AND expires_at >= ?
            """,
            (token, now_iso()),
        ).fetchone()
        if not row:
            raise ValidationError("Invalid or expired claim token.")
            
        user_id = row["user_id"]
        league_id = row["league_id"]
        from werkzeug.security import generate_password_hash
        hashed_password = generate_password_hash(password_raw)
        
        self._conn.execute(
            "UPDATE users SET display_name=?, password_hash=?, claimed_at=? WHERE id=?",
            (display_name, hashed_password, now_iso(), user_id),
        )
        self._conn.execute("UPDATE claim_tokens SET used_at=? WHERE id=?", (now_iso(), row["id"]))
        
        self._engine.journal.log(
            entity_type="user",
            entity_id=user_id,
            action="claim",
            message=f"Player account claimed by {display_name}.",
            league_id=league_id
        )
        self._engine.alerts.publish(
            title="Manager joined the league",
            body=f"{display_name} has claimed their team account.",
            kind="success",
            league_id=league_id
        )
        return user_id


class OpsAuditEngine:
    def __init__(self, conn: sqlite3.Connection, session_provider: SessionProvider):
        self.journal = JournalNamespace(conn, session_provider)
        self.alerts = AlertsNamespace(conn, session_provider)
        self.tokens = TokensNamespace(conn, session_provider)
        self.journal._engine = self
        self.alerts._engine = self
        self.tokens._engine = self


def get_ops_engine(conn):
    return OpsAuditEngine(conn, FlaskSessionProvider())


def get_effective_league_id(conn):
    from auth_support import LeagueScopeManager
    return LeagueScopeManager(conn).effective_league_id


def get_scoped_league_id(conn):
    from auth_support import LeagueScopeManager
    return LeagueScopeManager(conn).scoped_league_id


def active_notifications(conn, limit=5):
    return get_ops_engine(conn).alerts.list_active(limit)


def latest_event_banner(conn):
    league_id = get_scoped_league_id(conn)
    return conn.execute(
        """
        SELECT *
        FROM event_banners
        WHERE (? IS NULL OR league_id=?)
        ORDER BY event_date DESC, id DESC
        LIMIT 1
        """,
        (league_id, league_id),
    ).fetchone()


def scheduled_event_rows(conn, today_iso):
    league_id = get_scoped_league_id(conn)
    rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT eb.*,
                   COUNT(er.id) AS result_count,
                   COUNT(DISTINCT er.fighter_id) AS fighter_result_count,
                   SUM(CASE WHEN er.entry_status='draft' THEN 1 ELSE 0 END) AS draft_result_count,
                   SUM(CASE WHEN er.entry_status='complete' THEN 1 ELSE 0 END) AS complete_result_count
            FROM event_banners eb
            LEFT JOIN event_results er ON er.scheduled_event_id = eb.id
                AND (? IS NULL OR er.league_id=?)
            WHERE (? IS NULL OR eb.league_id=?)
            GROUP BY eb.id
            ORDER BY eb.event_date DESC, eb.event_name
            """,
            (league_id, league_id, league_id, league_id),
        ).fetchall()
    ]
    for row in rows:
        is_completed = row["event_date"] < today_iso or row["result_count"] > 0
        row["status_label"] = "Completed" if is_completed else "Scheduled"
        if row.get("draft_result_count"):
            row["status_label"] = "In Progress"
        row["display_label"] = f"{row['event_name']} ({row['event_date']})"
    return rows


def create_notification(conn, title, body, kind="update", expires_at=None):
    get_ops_engine(conn).alerts.publish(title, body, kind, expires_at)


def log_audit(
    conn,
    entity_type,
    entity_id,
    action,
    message,
    before_state=None,
    after_state=None,
    rollback_type=None,
    league_id=_AUDIT_LEAGUE_UNSET,
):
    resolved_league_id = None if league_id is _AUDIT_LEAGUE_UNSET else league_id
    get_ops_engine(conn).journal.log(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        message=message,
        before_state=before_state,
        after_state=after_state,
        rollback_type=rollback_type,
        league_id=resolved_league_id
    )


def team_state(conn, team_id):
    team = conn.execute("SELECT * FROM fantasy_teams WHERE id=?", (team_id,)).fetchone()
    if not team:
        return None
    fighters = conn.execute(
        "SELECT fighter_id, slot FROM fantasy_team_fighters WHERE team_id=? ORDER BY slot",
        (team_id,),
    ).fetchall()
    return {
        "team": dict(team),
        "fighters": [dict(row) for row in fighters],
    }


def event_state(conn, event_id):
    row = conn.execute("SELECT * FROM event_results WHERE id=?", (event_id,)).fetchone()
    return dict(row) if row else None


def event_result_audit_state(conn, event_id):
    row = conn.execute(
        """
        SELECT er.*,
               f.name AS fighter_name,
               eb.event_name AS scheduled_event_name
        FROM event_results er
        JOIN fighters f ON f.id = er.fighter_id
        LEFT JOIN event_banners eb ON eb.id = er.scheduled_event_id
        WHERE er.id=?
        """,
        (event_id,),
    ).fetchone()
    return dict(row) if row else None


def get_or_create_share_token(conn, team_id):
    return get_ops_engine(conn).tokens.get_or_create_share(team_id)


def create_claim_token(conn, user_id):
    return get_ops_engine(conn).tokens.issue_claim(user_id)


def active_claim_token_for_user(conn, user_id):
    return get_ops_engine(conn).tokens.active_for_user(user_id)


def audit_logs(conn, limit=100):
    return get_ops_engine(conn).journal.query(limit)
