import secrets
from functools import wraps
from datetime import datetime


def get_db_conn():
    from src.app import db
    return db()


from typing import Optional, List, Dict, Any

class LeagueScopeManager:
    """
    Decoupled scoping coordinator resolving user session, role, and league
    context from database and a session dictionary context.
    """
    def __init__(self, conn, session_dict=None, user_resolver=None):
        self._conn = conn
        if session_dict is None:
            from flask import has_request_context, session
            self._session = session if has_request_context() else {}
        else:
            self._session = session_dict
        self._user_resolver = user_resolver or self._default_user_resolver

    def _default_user_resolver(self):
        uid = self._session.get("user_id") if self._session else None
        if not uid:
            return None
        return self._conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()

    @property
    def current_user(self):
        return self._user_resolver()

    @property
    def current_user_id(self) -> Optional[int]:
        user = self.current_user
        return user["id"] if user else None

    @property
    def active_league_id(self) -> Optional[int]:
        return self._session.get("active_league_id") if self._session else None

    @property
    def is_site_admin(self) -> bool:
        user = self.current_user
        return bool(user and user["role"] in {"admin", "site_admin"})

    @property
    def effective_role(self) -> Optional[str]:
        user = self.current_user
        if not user:
            return None
        if self.is_site_admin:
            return "site_admin"
        membership = self.active_membership
        if membership and membership["status"] == "active":
            return membership["role"]
        return user["role"]

    @property
    def is_league_admin(self) -> bool:
        return self.effective_role == "league_admin"

    @property
    def is_admin_user(self) -> bool:
        return self.is_site_admin or self.is_league_admin

    @property
    def memberships(self) -> List[Any]:
        user = self.current_user
        if not user:
            return []
        return self._conn.execute(
            """
            SELECT *
            FROM league_memberships
            WHERE user_id=?
            ORDER BY
                CASE status
                    WHEN 'active' THEN 0
                    WHEN 'invited' THEN 1
                    WHEN 'inactive' THEN 2
                    ELSE 3
                END,
                league_id,
                id
            """,
            (user["id"],),
        ).fetchall()

    @property
    def active_membership(self):
        user = self.current_user
        if not user:
            return None
        active_league_id = self.active_league_id
        rows = self.memberships
        if not rows:
            return None
        if active_league_id is not None:
            for row in rows:
                if row["league_id"] == active_league_id and row["status"] == "active":
                    return row
        for row in rows:
            if row["status"] == "active":
                return row
        return rows[0]

    @property
    def current_user_league_id(self) -> Optional[int]:
        user = self.current_user
        if not user:
            return None
        membership = self.active_membership
        if membership:
            return membership["league_id"]
        return user["league_id"]

    @property
    def default_league_id(self) -> Optional[int]:
        from src.app import DEFAULT_LEAGUE_SLUG
        row = self._conn.execute("SELECT id FROM leagues WHERE slug=?", (DEFAULT_LEAGUE_SLUG,)).fetchone()
        return row["id"] if row else None

    @property
    def effective_league_id(self) -> Optional[int]:
        lid = self.current_user_league_id
        if lid is not None:
            return lid
        return self.default_league_id

    @property
    def scoped_league_id(self) -> Optional[int]:
        if self.is_site_admin:
            return None
        return self.effective_league_id

    @property
    def current_league(self):
        league_id = self.current_user_league_id
        if league_id:
            league = self._conn.execute("SELECT * FROM leagues WHERE id=?", (league_id,)).fetchone()
            if league:
                return league
        from src.app import DEFAULT_LEAGUE_SLUG
        return self._conn.execute("SELECT * FROM leagues WHERE slug=?", (DEFAULT_LEAGUE_SLUG,)).fetchone()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_user": self.current_user,
            "is_site_admin": self.is_site_admin,
            "is_league_admin": self.is_league_admin,
            "is_admin_user": self.is_admin_user,
            "scoped_league_id": self.scoped_league_id,
            "effective_league_id": self.effective_league_id,
            "active_membership": self.active_membership,
            "effective_role": self.effective_role,
        }


def current_user():
    from flask import has_request_context, session
    if not has_request_context():
        return None
    manager = LeagueScopeManager(get_db_conn(), session)
    return manager.current_user


def memberships_for_user(user_id):
    if not user_id:
        return []
    return get_db_conn().execute(
        """
        SELECT *
        FROM league_memberships
        WHERE user_id=?
        ORDER BY
            CASE status
                WHEN 'active' THEN 0
                WHEN 'invited' THEN 1
                WHEN 'inactive' THEN 2
                ELSE 3
            END,
            league_id,
            id
        """,
        (user_id,),
    ).fetchall()


def ensure_active_league_membership(conn, user_id, league_id, *, role, manager_limit):
    if not user_id or not league_id:
        return
    normalized_manager_limit = 1 if int(manager_limit or 0) > 0 else 0
    now = datetime.utcnow().replace(microsecond=0).isoformat()
    existing = conn.execute(
        """
        SELECT *
        FROM league_memberships
        WHERE user_id=? AND league_id=?
        """,
        (user_id, league_id),
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE league_memberships
            SET role=?,
                status='active',
                manager_limit=?,
                joined_at=COALESCE(joined_at, ?),
                left_at=NULL,
                updated_at=?
            WHERE id=?
            """,
            (role, normalized_manager_limit, now, now, existing["id"]),
        )
        return
    conn.execute(
        """
        INSERT INTO league_memberships(
            user_id,
            league_id,
            role,
            status,
            manager_limit,
            joined_at,
            created_at,
            updated_at
        )
        VALUES(?,?,?,?,?,?,?,?)
        """,
        (user_id, league_id, role, "active", normalized_manager_limit, now, now, now),
    )


def active_membership_for_user(user=None):
    from flask import session, has_request_context
    sess = session if has_request_context() else {}
    resolver = (lambda: user) if user is not None else None
    manager = LeagueScopeManager(get_db_conn(), sess, user_resolver=resolver)
    return manager.active_membership


def current_user_league_id(conn=None):
    from flask import session, has_request_context
    db_conn = conn or get_db_conn()
    sess = session if has_request_context() else {}
    manager = LeagueScopeManager(db_conn, sess)
    return manager.current_user_league_id


def current_league(conn=None):
    from flask import session, has_request_context
    db_conn = conn or get_db_conn()
    sess = session if has_request_context() else {}
    manager = LeagueScopeManager(db_conn, sess)
    return manager.current_league


def default_league_id(conn=None):
    db_conn = conn or get_db_conn()
    manager = LeagueScopeManager(db_conn, {})
    return manager.default_league_id


def effective_league_id(conn=None):
    from flask import session, has_request_context
    db_conn = conn or get_db_conn()
    sess = session if has_request_context() else {}
    manager = LeagueScopeManager(db_conn, sess)
    return manager.effective_league_id


def scoped_league_id(conn=None):
    from flask import session, has_request_context
    db_conn = conn or get_db_conn()
    sess = session if has_request_context() else {}
    manager = LeagueScopeManager(db_conn, sess)
    return manager.scoped_league_id


def is_site_admin(user):
    return bool(user and user["role"] in {"admin", "site_admin"})


def effective_role_for_user(user=None):
    from flask import session, has_request_context
    sess = session if has_request_context() else {}
    resolver = (lambda: user) if user is not None else None
    manager = LeagueScopeManager(get_db_conn(), sess, user_resolver=resolver)
    return manager.effective_role


def is_league_admin(user):
    return effective_role_for_user(user) == "league_admin"


def is_admin_user(user):
    return is_site_admin(user) or is_league_admin(user)


def csrf_token():
    from flask import session
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def protect_post_requests():
    from flask import request, session, flash, redirect, url_for
    if request.method != "POST":
        return None
    sent_token = request.form.get("_csrf_token", "")
    if not sent_token or sent_token != session.get("_csrf_token"):
        flash("Your session expired. Please try again.")
        target = request.referrer or url_for("login")
        return redirect(target)
    return None


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        from flask import flash, redirect, url_for
        if current_user() is None:
            flash("Please log in first.")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        from flask import abort
        user = current_user()
        if not is_admin_user(user):
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


def site_admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        from flask import abort
        user = current_user()
        if not is_site_admin(user):
            abort(403)
        return fn(*args, **kwargs)
    return wrapper
