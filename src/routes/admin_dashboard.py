from datetime import datetime, timedelta, timezone


def _format_quota_usage(used, quota):
    if quota is None:
        return f"{used} / Unlimited"
    return f"{used} / {quota}"


def _parse_activity_timestamp(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _quota_ratio(used, quota):
    if not quota:
        return 0
    return used / quota


def _reporting_snapshot(league_summaries):
    now = datetime.now(timezone.utc)
    attention_leagues = []
    active_count = 0
    pending_count = 0
    inactive_count = 0
    archived_count = 0
    stale_count = 0
    unassigned_count = 0
    near_capacity_count = 0
    recently_active_count = 0
    launch_queue = []
    inactive_leagues = []

    for summary in league_summaries:
        reasons = []
        status = (summary.get("status") or "").lower()
        if status == "active":
            active_count += 1
        elif status == "pending":
            pending_count += 1
            launch_queue.append(dict(summary))
            reasons.append("League is still pending launch.")
        elif status == "inactive":
            inactive_count += 1
            inactive_leagues.append(dict(summary))
            reasons.append("Status is inactive.")
        else:
            archived_count += 1
            reasons.append(f"Status is {summary.get('status', 'unknown')}.")

        if summary.get("league_admin_count", 0) == 0:
            unassigned_count += 1
            reasons.append("No league admin assigned.")

        activity_at = _parse_activity_timestamp(summary.get("recent_activity_at"))
        if activity_at and activity_at.tzinfo is None:
            activity_at = activity_at.replace(tzinfo=timezone.utc)
        if activity_at and (now - activity_at).days < 7:
            recently_active_count += 1
        stale = not activity_at or (now - activity_at).days >= 30
        if status == "active" and stale:
            stale_count += 1
            reasons.append("No activity in 30+ days.")

        player_ratio = _quota_ratio(summary.get("player_count", 0), summary.get("max_players"))
        team_ratio = _quota_ratio(summary.get("team_count", 0), summary.get("max_teams"))
        if player_ratio >= 0.8 or team_ratio >= 0.8:
            near_capacity_count += 1
            if player_ratio >= 0.8:
                reasons.append("Player quota is near capacity.")
            if team_ratio >= 0.8:
                reasons.append("Team quota is near capacity.")

        if reasons:
            attention_summary = dict(summary)
            attention_summary["attention_reasons"] = reasons
            attention_leagues.append(attention_summary)

    attention_leagues.sort(
        key=lambda league: (
            0 if (league.get("status") or "").lower() == "inactive" else 1,
            0 if league.get("league_admin_count", 0) == 0 else 1,
            league.get("name", ""),
        )
    )

    return {
        "active_count": active_count,
        "pending_count": pending_count,
        "inactive_count": inactive_count,
        "archived_count": archived_count,
        "attention_count": len(attention_leagues),
        "recently_active_count": recently_active_count,
        "stale_count": stale_count,
        "unassigned_count": unassigned_count,
        "near_capacity_count": near_capacity_count,
        "attention_leagues": attention_leagues[:6],
        "launch_queue": launch_queue[:6],
        "inactive_leagues": inactive_leagues[:6],
    }


def _league_summary_rows(conn, status_filter="all"):
    query = """
        SELECT
            l.*,
            COALESCE(player_counts.player_count, 0) AS player_count,
            COALESCE(team_counts.team_count, 0) AS team_count,
            COALESCE(league_admin_counts.league_admin_count, 0) AS league_admin_count,
            COALESCE(fighter_counts.fighter_count, 0) AS fighter_count,
            COALESCE(event_counts.event_count, 0) AS event_count,
            (
                SELECT MAX(activity_at)
                FROM (
                    SELECT l.updated_at AS activity_at
                    UNION ALL
                    SELECT al.created_at
                    FROM audit_logs al
                    WHERE al.league_id = l.id
                    UNION ALL
                    SELECT n.created_at
                    FROM notifications n
                    WHERE n.league_id = l.id
                    UNION ALL
                    SELECT er.event_date
                    FROM event_results er
                    WHERE er.league_id = l.id
                ) activity_stream
            ) AS recent_activity_at
        FROM leagues l
        LEFT JOIN (
            SELECT league_id, COUNT(*) AS player_count
            FROM league_memberships
            WHERE status='active'
              AND (role='player' OR manager_limit > 0)
            GROUP BY league_id
        ) player_counts ON player_counts.league_id = l.id
        LEFT JOIN (
            SELECT league_id, COUNT(*) AS team_count
            FROM fantasy_teams
            GROUP BY league_id
        ) team_counts ON team_counts.league_id = l.id
        LEFT JOIN (
            SELECT league_id, COUNT(*) AS league_admin_count
            FROM league_memberships
            WHERE status='active'
              AND role='league_admin'
            GROUP BY league_id
        ) league_admin_counts ON league_admin_counts.league_id = l.id
        LEFT JOIN (
            SELECT league_id, COUNT(*) AS fighter_count
            FROM fighters
            GROUP BY league_id
        ) fighter_counts ON fighter_counts.league_id = l.id
        LEFT JOIN (
            SELECT league_id, COUNT(DISTINCT event_name || event_date) AS event_count
            FROM event_results
            GROUP BY league_id
        ) event_counts ON event_counts.league_id = l.id
    """
    params = []
    if status_filter != "all":
        query += " WHERE l.status = ?"
        params.append(status_filter)
    query += """
        ORDER BY
            CASE l.status
                WHEN 'active' THEN 0
                WHEN 'pending' THEN 1
                WHEN 'inactive' THEN 2
                ELSE 3
            END,
            l.name
    """
    return conn.execute(query, tuple(params)).fetchall()


def _recent_platform_activity(conn, limit=8, window_days=30, status_filter="all"):
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=window_days)).replace(microsecond=0).isoformat()
    params = [cutoff, cutoff]
    status_sql = ""
    if status_filter != "all":
        status_sql = "WHERE league_status = ? OR league_status IS NULL"
        params.append(status_filter)
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT *
        FROM (
            SELECT
                'audit' AS activity_type,
                al.created_at AS activity_at,
                COALESCE(l.name, 'Platform') AS league_name,
                l.status AS league_status,
                al.message AS headline,
                al.action AS detail,
                'admin_audit' AS target_endpoint
            FROM audit_logs al
            LEFT JOIN leagues l ON l.id = al.league_id
            WHERE al.created_at >= ?
            UNION ALL
            SELECT
                'notification' AS activity_type,
                n.created_at AS activity_at,
                COALESCE(l.name, 'Platform') AS league_name,
                l.status AS league_status,
                n.title AS headline,
                n.kind AS detail,
                'admin_notifications' AS target_endpoint
            FROM notifications n
            LEFT JOIN leagues l ON l.id = n.league_id
            WHERE n.created_at >= ?
              AND n.league_id IS NULL
        ) activity_feed
        {status_sql}
        ORDER BY activity_at DESC
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()
    return [dict(row) for row in rows]


def _trend_delta(current_value, previous_value):
    if current_value == previous_value:
        return "steady"
    return "up" if current_value > previous_value else "down"


def _normalize_window_days(raw_value):
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return 30
    return value if value in (7, 30, 90) else 30


def _season_rows(conn):
    return conn.execute(
        """
        SELECT id, name, status, locked, completed_at
        FROM seasons
        ORDER BY id DESC
        """
    ).fetchall()


def _season_reporting(conn, season_id):
    if not season_id:
        return {
            "team_snapshot_count": 0,
            "fighter_snapshot_count": 0,
            "cost_change_count": 0,
        }
    return {
        "team_snapshot_count": conn.execute(
            "SELECT COUNT(*) FROM season_team_snapshots WHERE season_id=?",
            (season_id,),
        ).fetchone()[0],
        "fighter_snapshot_count": conn.execute(
            "SELECT COUNT(*) FROM season_fighter_snapshots WHERE season_id=?",
            (season_id,),
        ).fetchone()[0],
        "cost_change_count": conn.execute(
            "SELECT COUNT(*) FROM season_cost_changes WHERE season_id=?",
            (season_id,),
        ).fetchone()[0],
    }


def _trend_reporting(conn, window_days=30, status_filter="all"):
    now = datetime.now(timezone.utc)
    current_window_start = (now - timedelta(days=window_days)).replace(microsecond=0).isoformat()
    previous_window_start = (now - timedelta(days=window_days * 2)).replace(microsecond=0).isoformat()
    current_window_date = current_window_start[:10]
    previous_window_date = previous_window_start[:10]

    def league_status_clause(alias):
        if status_filter == "all":
            return "", []
        return f" JOIN leagues l ON l.id = {alias}.league_id WHERE l.status = ?", [status_filter]

    def scalar(query, params):
        return conn.execute(query, params).fetchone()[0]

    audit_join, audit_status_params = league_status_clause("al")
    notification_join, notification_status_params = league_status_clause("n")
    event_join, event_status_params = league_status_clause("er")
    membership_join, membership_status_params = league_status_clause("lm")

    audit_prefix = f"SELECT COUNT(*) FROM audit_logs al{audit_join}"
    audit_where = " WHERE" if "WHERE" not in audit_prefix else " AND"
    audit_last_window = scalar(
        f"{audit_prefix}{audit_where} al.created_at >= ?",
        tuple(audit_status_params + [current_window_start]),
    )
    audit_prev_window = scalar(
        f"{audit_prefix}{audit_where} al.created_at >= ? AND al.created_at < ?",
        tuple(audit_status_params + [previous_window_start, current_window_start]),
    )

    notification_prefix = f"SELECT COUNT(*) FROM notifications n{notification_join}"
    notification_where = " WHERE" if "WHERE" not in notification_prefix else " AND"
    notification_last_window = scalar(
        f"{notification_prefix}{notification_where} n.league_id IS NULL AND n.created_at >= ?",
        tuple(notification_status_params + [current_window_start]),
    )
    notification_prev_window = scalar(
        f"{notification_prefix}{notification_where} n.league_id IS NULL AND n.created_at >= ? AND n.created_at < ?",
        tuple(notification_status_params + [previous_window_start, current_window_start]),
    )

    event_prefix = f"SELECT COUNT(DISTINCT er.event_name || er.event_date) FROM event_results er{event_join}"
    event_where = " WHERE" if "WHERE" not in event_prefix else " AND"
    event_last_window = scalar(
        f"{event_prefix}{event_where} er.event_date >= ?",
        tuple(event_status_params + [current_window_date]),
    )
    event_prev_window = scalar(
        f"{event_prefix}{event_where} er.event_date >= ? AND er.event_date < ?",
        tuple(event_status_params + [previous_window_date, current_window_date]),
    )

    membership_prefix = f"SELECT COUNT(*) FROM league_memberships lm{membership_join}"
    membership_where = " WHERE" if "WHERE" not in membership_prefix else " AND"
    membership_last_window = scalar(
        f"{membership_prefix}{membership_where} lm.joined_at IS NOT NULL AND lm.joined_at >= ?",
        tuple(membership_status_params + [current_window_start]),
    )
    membership_prev_window = scalar(
        f"{membership_prefix}{membership_where} lm.joined_at IS NOT NULL AND lm.joined_at >= ? AND lm.joined_at < ?",
        tuple(membership_status_params + [previous_window_start, current_window_start]),
    )

    top_active_count_params = [current_window_start, current_window_start, current_window_date, current_window_start]
    top_active_status_sql = ""
    top_active_status_params = []
    if status_filter != "all":
        top_active_status_sql = "WHERE l.status = ?"
        top_active_status_params.append(status_filter)
    top_active_leagues = [
        dict(row)
        for row in conn.execute(
            """
            SELECT
                l.id,
                l.name,
                l.club_name,
                COALESCE((
                    SELECT COUNT(*)
                    FROM audit_logs al
                    WHERE al.league_id = l.id
                      AND al.created_at >= ?
                ), 0) AS audit_count_window,
                COALESCE((
                    SELECT COUNT(*)
                    FROM notifications n
                    WHERE n.league_id = l.id
                      AND n.created_at >= ?
                ), 0) AS notification_count_window,
                COALESCE((
                    SELECT COUNT(DISTINCT er.event_name || er.event_date)
                    FROM event_results er
                    WHERE er.league_id = l.id
                      AND er.event_date >= ?
                ), 0) AS event_count_window,
                COALESCE((
                    SELECT COUNT(*)
                    FROM league_memberships lm
                    WHERE lm.league_id = l.id
                      AND lm.joined_at IS NOT NULL
                      AND lm.joined_at >= ?
                ), 0) AS membership_join_count_window,
                (
                    COALESCE((
                        SELECT COUNT(*)
                        FROM audit_logs al
                        WHERE al.league_id = l.id
                          AND al.created_at >= ?
                    ), 0)
                    +
                    COALESCE((
                        SELECT COUNT(*)
                        FROM notifications n
                        WHERE n.league_id = l.id
                          AND n.created_at >= ?
                    ), 0)
                    +
                    COALESCE((
                        SELECT COUNT(DISTINCT er.event_name || er.event_date)
                        FROM event_results er
                        WHERE er.league_id = l.id
                          AND er.event_date >= ?
                    ), 0)
                    +
                    COALESCE((
                        SELECT COUNT(*)
                        FROM league_memberships lm
                        WHERE lm.league_id = l.id
                          AND lm.joined_at IS NOT NULL
                          AND lm.joined_at >= ?
                    ), 0)
                ) AS activity_score_30d
            FROM leagues l
            {status_sql}
            ORDER BY activity_score_30d DESC, l.name
            LIMIT 5
            """.format(status_sql=top_active_status_sql),
            tuple(top_active_count_params + top_active_count_params + top_active_status_params),
        ).fetchall()
    ]

    return {
        "window_days": window_days,
        "audit_last_window": audit_last_window,
        "audit_prev_window": audit_prev_window,
        "audit_trend": _trend_delta(audit_last_window, audit_prev_window),
        "notification_last_window": notification_last_window,
        "notification_prev_window": notification_prev_window,
        "notification_trend": _trend_delta(notification_last_window, notification_prev_window),
        "event_last_window": event_last_window,
        "event_prev_window": event_prev_window,
        "event_trend": _trend_delta(event_last_window, event_prev_window),
        "membership_last_window": membership_last_window,
        "membership_prev_window": membership_prev_window,
        "membership_trend": _trend_delta(membership_last_window, membership_prev_window),
        "top_active_leagues": top_active_leagues,
    }


def register_admin_dashboard_routes(app, deps):
    admin_required = deps["admin_required"]
    current_season = deps["current_season"]
    db = deps["db"]
    ensure_active_season = deps["ensure_active_season"]
    request = deps["request"]
    render_template = deps["render_template"]

    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        conn = db()
        current = current_season(conn) or ensure_active_season(conn)
        seasons = [dict(row) for row in _season_rows(conn)]
        selected_season_id = request.args.get("season", type=int)
        selected_status = (request.args.get("status") or "all").lower()
        if selected_status not in {"all", "active", "pending", "inactive", "archived"}:
            selected_status = "all"
        window_days = _normalize_window_days(request.args.get("window"))
        if not selected_season_id and current:
            selected_season_id = current["id"]
        selected_season = next((season for season in seasons if season["id"] == selected_season_id), None)
        if not selected_season and seasons:
            selected_season = seasons[0]
            selected_season_id = selected_season["id"]
        stats = {
            "leagues": conn.execute("SELECT COUNT(*) AS c FROM leagues").fetchone()["c"],
            "fighters": conn.execute("SELECT COUNT(*) AS c FROM fighters").fetchone()["c"],
            "teams": conn.execute("SELECT COUNT(*) AS c FROM fantasy_teams").fetchone()["c"],
            "players": conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM league_memberships
                WHERE status='active'
                  AND (role='player' OR manager_limit > 0)
                """
            ).fetchone()["c"],
            "events": conn.execute("SELECT COUNT(DISTINCT event_name || event_date) AS c FROM event_results").fetchone()["c"],
            "results": conn.execute("SELECT COUNT(*) AS c FROM event_results").fetchone()["c"],
            "notifications": conn.execute("SELECT COUNT(*) AS c FROM notifications WHERE is_active=1 AND league_id IS NULL").fetchone()["c"],
            "audit_entries": conn.execute("SELECT COUNT(*) AS c FROM audit_logs").fetchone()["c"],
        }
        latest_cost_changes = (
            conn.execute(
                """
                SELECT *
                FROM season_cost_changes
                WHERE season_id=?
                ORDER BY ABS(new_cost - old_cost) DESC, fighter_name
                LIMIT 8
                """,
                (selected_season_id,),
            ).fetchall()
            if selected_season_id
            else []
        )
        season_reporting = _season_reporting(conn, selected_season_id)
        league_summaries = []
        for row in _league_summary_rows(conn, selected_status):
            summary = dict(row)
            summary["player_quota_usage"] = _format_quota_usage(summary["player_count"], summary.get("max_players"))
            summary["team_quota_usage"] = _format_quota_usage(summary["team_count"], summary.get("max_teams"))
            league_summaries.append(summary)
        reporting = _reporting_snapshot(league_summaries)
        recent_activity = _recent_platform_activity(conn, window_days=window_days, status_filter=selected_status)
        trends = _trend_reporting(conn, window_days=window_days, status_filter=selected_status)
        return render_template(
            "admin_dashboard.html",
            stats=stats,
            season=current,
            selected_season=selected_season,
            selected_season_id=selected_season_id,
            seasons=seasons,
            season_reporting=season_reporting,
            latest_cost_changes=latest_cost_changes,
            league_summaries=league_summaries,
            reporting=reporting,
            recent_activity=recent_activity,
            trends=trends,
            filters={
                "status": selected_status,
                "window_days": window_days,
            },
        )
