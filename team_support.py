import os
import sqlite3
import secrets
import io
from pathlib import Path
from typing import List, Optional, BinaryIO, Protocol, Dict, Any
from dataclasses import dataclass, field

from exceptions import ValidationError
from player_support import player_rows, parse_int_field_from_value

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
BASE_DIR = Path(__file__).resolve().parent
TEAM_UPLOAD_DIR = BASE_DIR / "static" / "uploads" / "teams"
TEAM_UPLOAD_STATIC_PREFIX = "uploads/teams"


# =====================================================================
# Domain Data Containers
# =====================================================================

@dataclass(frozen=True)
class TeamFighter:
    fighter_id: int
    name: str
    current_cost: int
    slot: int


@dataclass(frozen=True)
class TeamDetails:
    team_id: Optional[int]
    team_name: str
    manager: str
    league_id: int
    player_user_id: Optional[int]
    image_path: Optional[str]
    image_credit: Optional[str]
    image_source_url: Optional[str]
    fighters: List[TeamFighter] = field(default_factory=list)


@dataclass(frozen=True)
class RosterChange:
    team_name: str
    manager: str
    player_user_id: Optional[int]
    fighter_ids: List[int]
    image_stream: Optional[BinaryIO] = None
    image_filename: Optional[str] = None
    image_credit: Optional[str] = None
    image_source_url: Optional[str] = None


# =====================================================================
# Abstract Ports
# =====================================================================

class TeamDatabasePort(Protocol):
    def check_season_editable(self, league_id: int) -> None: ...
    def is_name_unique(self, name: str, league_id: int, exclude_team_id: Optional[int]) -> bool: ...
    def is_manager_unique(self, manager: str, league_id: int, exclude_team_id: Optional[int]) -> bool: ...
    def get_fighter_costs_and_league(self, fighter_ids: List[int], league_id: int) -> Dict[int, int]: ...
    def get_player_slot_usage(self, player_user_id: int, league_id: int, exclude_team_id: Optional[int]) -> Dict[str, int]: ...
    def get_league_quota_summary(self, league_id: int) -> Dict[str, Any]: ...
    def get_league_settings(self, league_id: int) -> Dict[str, Any]: ...
    def get_team_details(self, team_id: int) -> Optional[TeamDetails]: ...
    def save_team_transaction(self, team_id: Optional[int], league_id: int, details: TeamDetails, fighter_ids: List[int]) -> int: ...
    def update_team_image_path(self, team_id: int, image_path: Optional[str]) -> None: ...
    def delete_team_transaction(self, team_id: int) -> None: ...
    def log_audit(self, action: str, entity_id: int, message: str, before_state: Optional[Dict[str, Any]], after_state: Optional[Dict[str, Any]], rollback_type: Optional[str] = None) -> None: ...
    def create_notification(self, title: str, body: str, kind: str) -> None: ...
    def commit(self) -> None: ...


class FileStoragePort(Protocol):
    def save_image(self, stream: BinaryIO, filename: str, team_id: int) -> str: ...
    def delete_image(self, path: str) -> None: ...


# =====================================================================
# Concrete Adapters
# =====================================================================

class SqliteTeamDatabaseAdapter(TeamDatabasePort):
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def check_season_editable(self, league_id: int) -> None:
        from season_support import require_active_season_editable
        require_active_season_editable(self.conn, "Team changes")

    def is_name_unique(self, name: str, league_id: int, exclude_team_id: Optional[int]) -> bool:
        row = self.conn.execute(
            """
            SELECT id FROM fantasy_teams
            WHERE lower(team_name)=lower(?)
              AND (? IS NULL OR league_id=?)
              AND (? IS NULL OR id != ?)
            """,
            (name, league_id, league_id, exclude_team_id, exclude_team_id),
        ).fetchone()
        return row is None

    def is_manager_unique(self, manager: str, league_id: int, exclude_team_id: Optional[int]) -> bool:
        row = self.conn.execute(
            """
            SELECT id FROM fantasy_teams
            WHERE lower(manager)=lower(?)
              AND (? IS NULL OR league_id=?)
              AND (? IS NULL OR id != ?)
            """,
            (manager, league_id, league_id, exclude_team_id, exclude_team_id),
        ).fetchone()
        return row is None

    def get_fighter_costs_and_league(self, fighter_ids: List[int], league_id: int) -> Dict[int, int]:
        if not fighter_ids:
            return {}
        placeholders = ",".join("?" for _ in fighter_ids)
        rows = self.conn.execute(
            f"SELECT id, current_cost FROM fighters WHERE league_id=? AND id IN ({placeholders})",
            (league_id, *fighter_ids),
        ).fetchall()
        return {row["id"]: row["current_cost"] for row in rows}

    def get_player_slot_usage(self, player_user_id: int, league_id: int, exclude_team_id: Optional[int]) -> Dict[str, int]:
        return player_manager_slot_usage(self.conn, player_user_id, exclude_team_id)

    def get_league_quota_summary(self, league_id: int) -> Dict[str, Any]:
        from quota_support import league_quota_summary
        return league_quota_summary(self.conn, league_id)

    def get_league_settings(self, league_id: int) -> Dict[str, Any]:
        return settings_dict(self.conn)

    def get_team_details(self, team_id: int) -> Optional[TeamDetails]:
        row = self.conn.execute(
            "SELECT * FROM fantasy_teams WHERE id=?", (team_id,)
        ).fetchone()
        if not row:
            return None
        
        fighter_rows = self.conn.execute(
            """
            SELECT ftf.fighter_id, f.name, f.current_cost, ftf.slot
            FROM fantasy_team_fighters ftf
            JOIN fighters f ON f.id = ftf.fighter_id
            WHERE ftf.team_id=?
            ORDER BY ftf.slot
            """,
            (team_id,)
        ).fetchall()
        
        fighters = [
            TeamFighter(
                fighter_id=r["fighter_id"],
                name=r["name"],
                current_cost=r["current_cost"],
                slot=r["slot"]
            )
            for r in fighter_rows
        ]
        
        return TeamDetails(
            team_id=row["id"],
            team_name=row["team_name"],
            manager=row["manager"],
            league_id=row["league_id"],
            player_user_id=row["player_user_id"],
            image_path=row["image_path"],
            image_credit=row["image_credit"],
            image_source_url=row["image_source_url"],
            fighters=fighters
        )

    def save_team_transaction(self, team_id: Optional[int], league_id: int, details: TeamDetails, fighter_ids: List[int]) -> int:
        if team_id is None:
            from quota_support import require_team_capacity
            require_team_capacity(self.conn, league_id)
            
            cur = self.conn.execute(
                """
                INSERT INTO fantasy_teams(team_name, manager, league_id, player_user_id, image_credit, image_source_url)
                VALUES(?,?,?,?,?,?)
                """,
                (details.team_name, details.manager, league_id, details.player_user_id, details.image_credit, details.image_source_url),
            )
            team_id = cur.lastrowid
        else:
            self.conn.execute(
                """
                UPDATE fantasy_teams
                SET team_name=?, manager=?, player_user_id=?, image_credit=?, image_source_url=?
                WHERE id=?
                """,
                (details.team_name, details.manager, details.player_user_id, details.image_credit, details.image_source_url, team_id),
            )
            self.conn.execute("DELETE FROM fantasy_team_fighters WHERE team_id=?", (team_id,))
            
        for slot, fighter_id in enumerate(fighter_ids, start=1):
            self.conn.execute(
                "INSERT INTO fantasy_team_fighters(team_id, fighter_id, slot) VALUES(?,?,?)",
                (team_id, fighter_id, slot),
            )
            
        return team_id

    def update_team_image_path(self, team_id: int, image_path: Optional[str]) -> None:
        self.conn.execute("UPDATE fantasy_teams SET image_path=? WHERE id=?", (image_path, team_id))

    def delete_team_transaction(self, team_id: int) -> None:
        self.conn.execute("DELETE FROM fantasy_team_fighters WHERE team_id=?", (team_id,))
        self.conn.execute("DELETE FROM team_share_links WHERE team_id=?", (team_id,))
        self.conn.execute("DELETE FROM fantasy_teams WHERE id=?", (team_id,))

    def log_audit(self, action: str, entity_id: int, message: str, before_state: Optional[Dict[str, Any]], after_state: Optional[Dict[str, Any]], rollback_type: Optional[str] = None) -> None:
        from ops_support import log_audit
        log_audit(self.conn, "team", entity_id, action, message, before_state=before_state, after_state=after_state, rollback_type=rollback_type)

    def create_notification(self, title: str, body: str, kind: str) -> None:
        from ops_support import create_notification
        create_notification(self.conn, title, body, kind)

    def commit(self) -> None:
        self.conn.commit()


class LocalFileSystemStorageAdapter(FileStoragePort):
    def __init__(self, upload_dir: Path, static_prefix: str, allowed_extensions: set):
        self.upload_dir = upload_dir
        self.static_prefix = static_prefix
        self.allowed_extensions = allowed_extensions

    def save_image(self, stream: BinaryIO, filename: str, team_id: int) -> str:
        from werkzeug.utils import secure_filename
        
        sec_name = secure_filename(filename)
        extension = sec_name.rsplit(".", 1)[-1].lower() if "." in sec_name else ""
        if extension not in self.allowed_extensions:
            raise ValidationError("Team image must be a JPG, PNG, GIF, or WebP file.")
            
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        stored_name = f"team-{team_id}-{secrets.token_hex(8)}.{extension}"
        
        target_path = self.upload_dir / stored_name
        with open(target_path, "wb") as f:
            f.write(stream.read())
            
        return f"{self.static_prefix}/{stored_name}"

    def delete_image(self, path: str) -> None:
        if not path:
            return
        image_file = BASE_DIR / "static" / path
        upload_root = self.upload_dir.resolve()
        try:
            resolved = image_file.resolve()
        except OSError:
            return
        if upload_root in resolved.parents and resolved.exists():
            resolved.unlink()


# =====================================================================
# Team Manager Subsystem
# =====================================================================

class TeamManager:
    def __init__(self, db_adapter: TeamDatabasePort, storage_adapter: FileStoragePort):
        self.db = db_adapter
        self.storage = storage_adapter

    def save_team(self, team_id: Optional[int], league_id: int, changes: RosterChange) -> int:
        # 1. Check active season status (raises ValidationError directly)
        self.db.check_season_editable(league_id)

        # 2. Check team name uniqueness
        if not self.db.is_name_unique(changes.team_name, league_id, team_id):
            raise ValidationError("That team name is already in use.")

        # 3. Check manager uniqueness
        if not self.db.is_manager_unique(changes.manager, league_id, team_id):
            raise ValidationError("That manager is already assigned to another team.")

        # 4. Check player manager slot quota
        if changes.player_user_id is not None:
            slot_usage = self.db.get_player_slot_usage(changes.player_user_id, league_id, team_id)
            if slot_usage:
                if slot_usage["limit"] <= 0:
                    raise ValidationError("That player is not enabled to own a team in this league.")
                if slot_usage["used"] >= slot_usage["limit"]:
                    raise ValidationError("That player already has a team in this league.")

        # 5. Check league context and duplicate fighters
        costs_map = self.db.get_fighter_costs_and_league(changes.fighter_ids, league_id)
        if len(costs_map) != len(set(changes.fighter_ids)):
            raise ValidationError("All selected fighters must belong to the same league as the team.")

        # 6. Capture before state
        before_state = None
        old_image_path = None
        if team_id is not None:
            from ops_support import team_state
            before_state = team_state(self.db.conn, team_id)
            if before_state:
                old_image_path = before_state["team"].get("image_path")

        # 7. Write database records in a transaction
        details = TeamDetails(
            team_id=team_id,
            team_name=changes.team_name,
            manager=changes.manager,
            league_id=league_id,
            player_user_id=changes.player_user_id,
            image_path=old_image_path,
            image_credit=changes.image_credit,
            image_source_url=changes.image_source_url
        )

        try:
            saved_team_id = self.db.save_team_transaction(team_id, league_id, details, changes.fighter_ids)
            
            new_image_path = None
            if changes.image_stream is not None and changes.image_filename is not None:
                new_image_path = self.storage.save_image(changes.image_stream, changes.image_filename, saved_team_id)
                self.db.update_team_image_path(saved_team_id, new_image_path)
                
        except Exception as exc:
            if 'new_image_path' in locals() and new_image_path:
                try:
                    self.storage.delete_image(new_image_path)
                except Exception:
                    pass
            raise exc

        from ops_support import team_state
        after_state = team_state(self.db.conn, saved_team_id)

        if team_id is None:
            self.db.log_audit("create", saved_team_id, f"Created team {changes.team_name}.", before_state=None, after_state=after_state)
        else:
            self.db.log_audit("update", saved_team_id, f"Updated team {changes.team_name}.", before_state=before_state, after_state=after_state, rollback_type="team_update")
            self.db.create_notification("Team standings may have shifted", f"{changes.team_name} was updated and the board has been recalculated.", "update")

        self.db.commit()

        if new_image_path and old_image_path:
            self.storage.delete_image(old_image_path)

        return saved_team_id

    def delete_team(self, team_id: int) -> Dict[str, Any]:
        details = self.db.get_team_details(team_id)
        if not details:
            raise ValidationError("Team does not exist.")

        # Check active season status (raises ValidationError directly)
        self.db.check_season_editable(details.league_id)

        from ops_support import team_state
        before_state = team_state(self.db.conn, team_id)
        if not before_state:
            raise ValidationError("Team does not exist.")

        self.db.delete_team_transaction(team_id)
        self.db.log_audit("delete", team_id, f"Deleted team {details.team_name}.", before_state=before_state, after_state=None)
        self.db.commit()

        if details.image_path:
            self.storage.delete_image(details.image_path)

        return before_state


# =====================================================================
# Compatibility Helpers & Wrappers
# =====================================================================

def int_setting(settings, key, default=0):
    try:
        return int(float(settings.get(key, default)))
    except Exception:
        return default


def settings_dict(conn):
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings").fetchall()}


def player_record(conn, user_id):
    if user_id is None:
        return None
    return conn.execute(
        "SELECT id, league_id FROM users WHERE id=? AND role='player'",
        (user_id,),
    ).fetchone()


def team_record(conn, team_id):
    if team_id is None:
        return None
    return conn.execute(
        "SELECT id, league_id, player_user_id FROM fantasy_teams WHERE id=?",
        (team_id,),
    ).fetchone()


def resolve_target_league_id(conn, team_id, player_user_id):
    existing_team = team_record(conn, team_id)
    if existing_team:
        target_league_id = existing_team["league_id"]
    else:
        target_league_id = None
    if player_user_id is None:
        if target_league_id is not None:
            return target_league_id
        from ops_support import get_effective_league_id
        return get_effective_league_id(conn)
    player = player_record(conn, player_user_id)
    if not player:
        raise ValidationError("Selected player does not exist.")
    player_league_id = player["league_id"]
    if target_league_id is None:
        return player_league_id
    if player_league_id != target_league_id:
        raise ValidationError("Selected player must belong to the same league as the team.")
    return target_league_id


def validate_team_fighters(conn, fighter_ids, target_league_id):
    if not fighter_ids:
        return
    placeholders = ",".join("?" for _ in fighter_ids)
    rows = conn.execute(
        f"SELECT id FROM fighters WHERE league_id=? AND id IN ({placeholders})",
        (target_league_id, *fighter_ids),
    ).fetchall()
    if len(rows) != len(set(fighter_ids)):
        raise ValidationError("All selected fighters must belong to the same league as the team.")


def player_manager_slot_usage(conn, user_id, exclude_team_id=None):
    from ops_support import get_scoped_league_id
    league_id = get_scoped_league_id(conn)
    player = conn.execute(
        """
        SELECT
            u.id,
            COALESCE(lm.manager_limit, u.manager_limit) AS manager_limit
        FROM users u
        LEFT JOIN league_memberships lm
          ON lm.user_id = u.id
         AND lm.league_id = ?
         AND lm.status = 'active'
        WHERE u.id=?
          AND (
            u.role='player'
            OR (lm.id IS NOT NULL AND (lm.role='player' OR lm.manager_limit > 0))
          )
          AND (? IS NULL OR COALESCE(lm.league_id, u.league_id)=?)
        """,
        (league_id, user_id, league_id, league_id),
    ).fetchone()
    if not player:
        return None
    used = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM fantasy_teams
        WHERE player_user_id=?
          AND (? IS NULL OR league_id=?)
          AND (? IS NULL OR id != ?)
        """,
        (user_id, league_id, league_id, exclude_team_id, exclude_team_id),
    ).fetchone()["c"]
    limit = 1 if int(player["manager_limit"] or 0) > 0 else 0
    return {"used": used, "limit": limit, "remaining": max(0, limit - used)}


def team_builder_context(conn):
    settings = settings_dict(conn)
    from app import leaderboard_rows
    fighters = leaderboard_rows(conn)
    return {
        "fighters": fighters,
        "fighter_profiles": [dict(row) for row in fighters],
        "players": player_rows(conn),
        "team_budget": int_setting(settings, "team_budget", 500),
        "minimum_team_size": int_setting(settings, "minimum_team_size", 5),
        "maximum_team_size": int_setting(settings, "maximum_team_size", 8),
    }


def parse_optional_player_user_id(conn):
    from flask import request
    raw = request.form.get("player_user_id", "").strip()
    if not raw:
        return None
    user_id = parse_int_field_from_value("player_user_id", raw, minimum=1)
    if not conn.execute("SELECT 1 FROM users WHERE id=? AND role='player'", (user_id,)).fetchone():
        raise ValidationError("Selected player does not exist.")
    return user_id


def team_form_values(conn, player_user_id_override=None):
    from flask import request
    team_name = request.form.get("team_name", "").strip()
    manager = request.form.get("manager", "").strip()
    if not team_name:
        raise ValidationError("Team name is required.")
    if not manager:
        raise ValidationError("Manager is required.")
    player_user_id = player_user_id_override if player_user_id_override is not None else parse_optional_player_user_id(conn)
    fighter_ids = []
    for raw in request.form.getlist("fighter_ids"):
        raw = raw.strip()
        if raw:
            fighter_ids.append(parse_int_field_from_value("fighter_ids", raw, minimum=1))
    image_credit = request.form.get("image_credit", "").strip()
    image_source_url = request.form.get("image_source_url", "").strip()
    return team_name, manager, player_user_id, fighter_ids, image_credit, image_source_url


def save_team(conn, team_id=None, forced_player_user_id=None):
    from flask import request
    
    db_adapter = SqliteTeamDatabaseAdapter(conn)
    storage_adapter = LocalFileSystemStorageAdapter(
        upload_dir=TEAM_UPLOAD_DIR,
        static_prefix=TEAM_UPLOAD_STATIC_PREFIX,
        allowed_extensions=ALLOWED_IMAGE_EXTENSIONS
    )
    
    manager = TeamManager(db_adapter, storage_adapter)
    
    team_name, manager_name, player_user_id, fighter_ids, image_credit, image_source_url = team_form_values(conn, forced_player_user_id)
    
    upload = request.files.get("team_image")
    image_stream = None
    image_filename = None
    if upload and upload.filename:
        image_stream = io.BytesIO(upload.read())
        image_filename = upload.filename
        
    target_league_id = resolve_target_league_id(conn, team_id, player_user_id)
    
    changes = RosterChange(
        team_name=team_name,
        manager=manager_name,
        player_user_id=player_user_id,
        fighter_ids=fighter_ids,
        image_stream=image_stream,
        image_filename=image_filename,
        image_credit=image_credit,
        image_source_url=image_source_url
    )
    
    return manager.save_team(team_id, target_league_id, changes)


def delete_team(conn, team_id):
    db_adapter = SqliteTeamDatabaseAdapter(conn)
    storage_adapter = LocalFileSystemStorageAdapter(
        upload_dir=TEAM_UPLOAD_DIR,
        static_prefix=TEAM_UPLOAD_STATIC_PREFIX,
        allowed_extensions=ALLOWED_IMAGE_EXTENSIONS
    )
    
    manager = TeamManager(db_adapter, storage_adapter)
    return manager.delete_team(team_id)
