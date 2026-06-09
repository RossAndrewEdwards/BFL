import re
from exceptions import ValidationError


def team_builder_context(conn):
    import team_support
    return team_support.team_builder_context(conn)


def parse_int_field_from_value(name, raw, minimum=None):
    label = name.replace("_", " ").title()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValidationError(f"{label} must be a whole number.") from exc
    if minimum is not None and value < minimum:
        raise ValidationError(f"{label} must be at least {minimum}.")
    return value


def valid_team_id(conn, team_id):
    if team_id is None:
        return True
    from auth_support import scoped_league_id
    league_id = scoped_league_id()
    return conn.execute(
        "SELECT 1 FROM fantasy_teams WHERE id=? AND (? IS NULL OR league_id=?)",
        (team_id, league_id, league_id),
    ).fetchone() is not None


def valid_player_user_id(conn, user_id):
    if user_id is None:
        return True
    from auth_support import scoped_league_id
    league_id = scoped_league_id()
    if league_id is None:
        return conn.execute(
            "SELECT 1 FROM users WHERE id=? AND role='player'",
            (user_id,),
        ).fetchone() is not None
    return conn.execute(
        """
        SELECT 1
        FROM league_memberships
        WHERE user_id=?
          AND league_id=?
          AND status='active'
          AND (role='player' OR manager_limit > 0)
        """,
        (user_id, league_id),
    ).fetchone() is not None


def player_manager_slot_usage(conn, user_id, exclude_team_id=None):
    import team_support
    return team_support.player_manager_slot_usage(conn, user_id, exclude_team_id)


def parse_optional_player_user_id(conn):
    from flask import request
    raw = request.form.get("player_user_id", "").strip()
    if not raw:
        return None
    user_id = parse_int_field_from_value("player_user_id", raw, minimum=1)
    if not valid_player_user_id(conn, user_id):
        raise ValidationError("Selected player does not exist.")
    return user_id


def parse_optional_team_id(conn):
    from flask import request
    raw = request.form.get("team_id", "").strip()
    if not raw:
        return None
    team_id = parse_int_field_from_value("team_id", raw, minimum=1)
    if not valid_team_id(conn, team_id):
        raise ValidationError("Selected team does not exist.")
    return team_id


def player_form_values(conn, require_password=False):
    from flask import request
    username = request.form.get("username", "").strip().lower()
    display_name = request.form.get("display_name", "").strip()
    if not username:
        raise ValidationError("Username is required.")
    if not re.fullmatch(r"[a-z0-9_]+", username):
        raise ValidationError("Username may only contain lowercase letters, numbers, and underscores.")
    if not display_name:
        raise ValidationError("Display name is required.")
    password = request.form.get("password", "")
    if require_password and not password:
        raise ValidationError("Password is required.")
    return {
        "username": username,
        "display_name": display_name,
        "password": password,
        "manager_limit": 1,
    }


def submitted_player_form(existing=None):
    from flask import request
    player = dict(existing) if existing else {}
    player["username"] = request.form.get("username", player.get("username", "")).strip().lower()
    player["display_name"] = request.form.get("display_name", player.get("display_name", "")).strip()
    player["manager_limit"] = 1
    return player


def team_fighter_ids(conn, team_id):
    if not team_id:
        return []
    return [row["fighter_id"] for row in conn.execute("SELECT fighter_id FROM fantasy_team_fighters WHERE team_id=? ORDER BY slot", (team_id,)).fetchall()]


def teams_for_player(conn, user_id):
    from auth_support import scoped_league_id
    league_id = scoped_league_id()
    return conn.execute(
        """
        SELECT id, team_name, manager
        FROM fantasy_teams
        WHERE player_user_id=?
          AND (? IS NULL OR league_id=?)
        ORDER BY team_name
        """,
        (user_id, league_id, league_id),
    ).fetchall()


def player_rows(conn):
    from app import request_cached
    from auth_support import scoped_league_id
    scoped_league_id_val = scoped_league_id()
    return request_cached(
        "player_rows",
        lambda: conn.execute(
            """
            SELECT
                u.id,
                u.username,
                u.display_name,
                u.password_hash,
                u.claimed_at,
                COALESCE(lm.role, u.role) AS membership_role,
                COALESCE(lm.manager_limit, u.manager_limit) AS manager_limit,
                COALESCE(lm.league_id, u.league_id) AS league_id,
                GROUP_CONCAT(ft.team_name, ', ') AS team_names,
                COUNT(ft.id) AS managed_team_count,
                CASE
                    WHEN COALESCE(lm.manager_limit, u.manager_limit) > COUNT(ft.id) THEN COALESCE(lm.manager_limit, u.manager_limit) - COUNT(ft.id)
                    ELSE 0
                END AS manager_slots_remaining
            FROM users u
            LEFT JOIN league_memberships lm
              ON lm.user_id = u.id
             AND (? IS NOT NULL)
             AND lm.league_id=?
             AND lm.status='active'
            LEFT JOIN fantasy_teams ft ON ft.player_user_id = u.id
                AND ((? IS NULL) OR ft.league_id=?)
            WHERE (
                (? IS NULL AND u.role='player')
                OR (? IS NOT NULL AND lm.id IS NOT NULL AND (lm.role='player' OR lm.manager_limit > 0))
            )
              AND (? IS NULL OR COALESCE(lm.league_id, u.league_id)=?)
            GROUP BY u.id, u.username, u.display_name, u.password_hash, u.claimed_at, COALESCE(lm.role, u.role), COALESCE(lm.manager_limit, u.manager_limit), COALESCE(lm.league_id, u.league_id)
            ORDER BY u.display_name, u.username
            """,
            (
                scoped_league_id_val,
                scoped_league_id_val,
                scoped_league_id_val,
                scoped_league_id_val,
                scoped_league_id_val,
                scoped_league_id_val,
                scoped_league_id_val,
                scoped_league_id_val,
            ),
        ).fetchall(),
    )


def selected_fighter_ids_from_form():
    from flask import request
    fighter_ids = []
    for raw in request.form.getlist("fighter_ids"):
        raw = raw.strip()
        if raw:
            fighter_ids.append(parse_int_field_from_value("fighter_ids", raw, minimum=1))
    return fighter_ids


def team_form_values(conn, player_user_id_override=None):
    import team_support
    return team_support.team_form_values(conn, player_user_id_override)
