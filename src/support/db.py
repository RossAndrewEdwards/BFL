import json
import os
import re
import sqlite3

from flask import g


def get_db(db_path, ensure_runtime_tables_fn):
    if "db" not in g:
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        ensure_runtime_tables_fn(g.db)
    return g.db


def ensure_runtime_tables(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS external_cache (
            key TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            refreshed_at TEXT NOT NULL
        )
        """
    )


def close_db():
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def execute_many(conn, sql, rows):
    conn.executemany(sql, rows)


def ensure_indexes(conn):
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_leagues_status_name ON leagues(status, name);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_leagues_join_code ON leagues(join_code);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_league_memberships_user_league ON league_memberships(user_id, league_id);
        CREATE INDEX IF NOT EXISTS idx_league_memberships_user_status ON league_memberships(user_id, status, league_id);
        CREATE INDEX IF NOT EXISTS idx_league_memberships_league_role ON league_memberships(league_id, role, status);
        CREATE INDEX IF NOT EXISTS idx_event_results_fighter_date ON event_results(fighter_id, event_date DESC);
        CREATE INDEX IF NOT EXISTS idx_event_results_league_date ON event_results(league_id, event_date DESC);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_event_results_scheduled_fighter ON event_results(scheduled_event_id, fighter_id) WHERE scheduled_event_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_event_results_scheduled_group ON event_results(scheduled_event_id, group_name, entry_status);
        CREATE INDEX IF NOT EXISTS idx_fantasy_team_fighters_team_slot ON fantasy_team_fighters(team_id, slot);
        CREATE INDEX IF NOT EXISTS idx_fantasy_team_fighters_fighter ON fantasy_team_fighters(fighter_id);
        CREATE INDEX IF NOT EXISTS idx_fantasy_teams_player ON fantasy_teams(player_user_id);
        CREATE INDEX IF NOT EXISTS idx_fantasy_teams_league ON fantasy_teams(league_id, id DESC);
        CREATE INDEX IF NOT EXISTS idx_users_role_display ON users(role, display_name, username);
        CREATE INDEX IF NOT EXISTS idx_users_league_role ON users(league_id, role, display_name);
        CREATE INDEX IF NOT EXISTS idx_fighters_league_name ON fighters(league_id, name);
        CREATE INDEX IF NOT EXISTS idx_claim_tokens_user_active ON claim_tokens(user_id, used_at, expires_at);
        CREATE INDEX IF NOT EXISTS idx_claim_tokens_league_active ON claim_tokens(league_id, used_at, expires_at);
        CREATE INDEX IF NOT EXISTS idx_notifications_active_created ON notifications(is_active, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_notifications_league_active_created ON notifications(league_id, is_active, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_fighter_change_requests_league_status_created ON fighter_change_requests(league_id, status, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_fighter_change_requests_requester_created ON fighter_change_requests(requester_user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_fighter_honours_fighter_date ON fighter_honours(fighter_id, awarded_on DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_fighter_honours_league_date ON fighter_honours(league_id, awarded_on DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_training_groups_league_name ON training_groups(league_id, name);
        CREATE INDEX IF NOT EXISTS idx_training_group_members_group_position ON training_group_members(training_group_id, position, id);
        CREATE INDEX IF NOT EXISTS idx_training_group_members_fighter ON training_group_members(fighter_id);
        CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(id DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_logs_league_created ON audit_logs(league_id, id DESC);
        CREATE INDEX IF NOT EXISTS idx_seasons_status ON seasons(status, id DESC);
        CREATE INDEX IF NOT EXISTS idx_season_team_snapshots_rank ON season_team_snapshots(season_id, rank);
        CREATE INDEX IF NOT EXISTS idx_season_fighter_snapshots_points ON season_fighter_snapshots(season_id, rank);
        CREATE INDEX IF NOT EXISTS idx_season_cost_changes_fighter ON season_cost_changes(season_id, fighter_id);
        CREATE INDEX IF NOT EXISTS idx_attendance_scores_fighter_type_date ON attendance_scores(fighter_id, score_type, attendance_date DESC);
        CREATE INDEX IF NOT EXISTS idx_attendance_scores_league_date ON attendance_scores(league_id, attendance_date DESC);
        CREATE INDEX IF NOT EXISTS idx_attendance_scores_season ON attendance_scores(season_id, score_type);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_event_banners_league_name_date ON event_banners(league_id, event_name, event_date);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_event_banners_league_external_key ON event_banners(league_id, external_key) WHERE external_key IS NOT NULL;
        """
    )


def init_db(config):
    conn = sqlite3.connect(config["db_path"])
    conn.row_factory = sqlite3.Row

    def backfill_league_memberships(default_joined_at):
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
            SELECT
                u.id,
                u.league_id,
                u.role,
                'active',
                COALESCE(u.manager_limit, 1),
                COALESCE(u.claimed_at, ?),
                ?,
                ?
            FROM users u
            WHERE u.role IN ('league_admin', 'player')
              AND u.league_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM league_memberships lm
                  WHERE lm.user_id = u.id
                    AND lm.league_id = u.league_id
              )
            """,
            (default_joined_at, default_joined_at, default_joined_at),
        )

    conn.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS leagues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            club_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('pending','active','inactive','archived')),
            description TEXT,
            contact_email TEXT,
            logo_url TEXT,
            join_code TEXT,
            max_players INTEGER,
            max_teams INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('site_admin','league_admin','player')),
            team_id INTEGER,
            manager_limit INTEGER NOT NULL DEFAULT 1,
            league_id INTEGER,
            FOREIGN KEY(league_id) REFERENCES leagues(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS league_memberships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            league_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('league_admin','player')),
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','invited','inactive','removed')),
            manager_limit INTEGER NOT NULL DEFAULT 1,
            joined_at TEXT,
            invited_at TEXT,
            left_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(league_id) REFERENCES leagues(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS rules (
            key TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            points INTEGER NOT NULL,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS ownership_brackets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lower_bound REAL NOT NULL,
            adjustment INTEGER NOT NULL,
            meaning TEXT
        );
        CREATE TABLE IF NOT EXISTS fighters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            spreadsheet_id TEXT UNIQUE,
            name TEXT UNIQUE NOT NULL,
            league_id INTEGER,
            tier TEXT NOT NULL,
            height REAL,
            weight REAL,
            age INTEGER,
            active INTEGER NOT NULL DEFAULT 1,
            start_year INTEGER,
            current_cost INTEGER NOT NULL,
            next_season_cost INTEGER,
            notes TEXT,
            nickname TEXT,
            fighting_style TEXT,
            preferred_role TEXT,
            role_or_weapon TEXT,
            known_for TEXT,
            why_buhurt TEXT,
            joined_year INTEGER,
            reputation TEXT,
            fantasy_insight TEXT,
            image_url TEXT,
            image_credit TEXT,
            image_source_url TEXT,
            FOREIGN KEY(league_id) REFERENCES leagues(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS baseline_stats (
            fighter_id INTEGER PRIMARY KEY,
            training INTEGER NOT NULL DEFAULT 0,
            support INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(fighter_id) REFERENCES fighters(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS attendance_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fighter_id INTEGER NOT NULL,
            league_id INTEGER,
            season_id INTEGER,
            score_type TEXT NOT NULL,
            score_units INTEGER NOT NULL DEFAULT 1,
            attendance_date TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL,
            created_by_user_id INTEGER,
            FOREIGN KEY(fighter_id) REFERENCES fighters(id) ON DELETE CASCADE,
            FOREIGN KEY(league_id) REFERENCES leagues(id) ON DELETE SET NULL,
            FOREIGN KEY(season_id) REFERENCES seasons(id) ON DELETE SET NULL,
            FOREIGN KEY(created_by_user_id) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS fighter_import_totals (
            fighter_id INTEGER PRIMARY KEY,
            training INTEGER NOT NULL DEFAULT 0,
            competitions INTEGER NOT NULL DEFAULT 0,
            rounds_fought INTEGER NOT NULL DEFAULT 0,
            support INTEGER NOT NULL DEFAULT 0,
            special_awards INTEGER NOT NULL DEFAULT 0,
            gold_medals INTEGER NOT NULL DEFAULT 0,
            silver_medals INTEGER NOT NULL DEFAULT 0,
            bronze_medals INTEGER NOT NULL DEFAULT 0,
            kills INTEGER NOT NULL DEFAULT 0,
            assists INTEGER NOT NULL DEFAULT 0,
            deaths INTEGER NOT NULL DEFAULT 0,
            sit_downs INTEGER NOT NULL DEFAULT 0,
            yellow_cards INTEGER NOT NULL DEFAULT 0,
            red_cards INTEGER NOT NULL DEFAULT 0,
            ownership_percent REAL NOT NULL DEFAULT 0,
            imported_at TEXT NOT NULL,
            FOREIGN KEY(fighter_id) REFERENCES fighters(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS event_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scheduled_event_id INTEGER,
            league_id INTEGER,
            event_date TEXT NOT NULL,
            event_name TEXT NOT NULL,
            fighter_id INTEGER NOT NULL,
            group_name TEXT,
            entry_status TEXT NOT NULL DEFAULT 'draft',
            updated_at TEXT,
            rounds_fought INTEGER NOT NULL DEFAULT 0,
            special_awards INTEGER NOT NULL DEFAULT 0,
            gold_medals INTEGER NOT NULL DEFAULT 0,
            silver_medals INTEGER NOT NULL DEFAULT 0,
            bronze_medals INTEGER NOT NULL DEFAULT 0,
            kills INTEGER NOT NULL DEFAULT 0,
            assists INTEGER NOT NULL DEFAULT 0,
            deaths INTEGER NOT NULL DEFAULT 0,
            sit_downs INTEGER NOT NULL DEFAULT 0,
            yellow_cards INTEGER NOT NULL DEFAULT 0,
            red_cards INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(fighter_id) REFERENCES fighters(id) ON DELETE CASCADE,
            FOREIGN KEY(league_id) REFERENCES leagues(id) ON DELETE SET NULL,
            FOREIGN KEY(scheduled_event_id) REFERENCES event_banners(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS fantasy_teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_name TEXT UNIQUE NOT NULL,
            manager TEXT NOT NULL,
            league_id INTEGER,
            player_user_id INTEGER,
            image_path TEXT,
            image_credit TEXT,
            image_source_url TEXT,
            FOREIGN KEY(league_id) REFERENCES leagues(id) ON DELETE SET NULL,
            FOREIGN KEY(player_user_id) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS fantasy_team_fighters (
            team_id INTEGER NOT NULL,
            fighter_id INTEGER NOT NULL,
            slot INTEGER NOT NULL,
            PRIMARY KEY(team_id, slot),
            FOREIGN KEY(team_id) REFERENCES fantasy_teams(id) ON DELETE CASCADE,
            FOREIGN KEY(fighter_id) REFERENCES fighters(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS claim_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            league_id INTEGER,
            token TEXT UNIQUE NOT NULL,
            code TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(league_id) REFERENCES leagues(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id INTEGER,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'update',
            created_at TEXT NOT NULL,
            expires_at TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(league_id) REFERENCES leagues(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS fighter_change_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id INTEGER NOT NULL,
            fighter_id INTEGER,
            requester_user_id INTEGER NOT NULL,
            reviewed_by_user_id INTEGER,
            request_type TEXT NOT NULL CHECK(request_type IN ('edit','create')),
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','denied')),
            payload_json TEXT NOT NULL,
            review_notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            reviewed_at TEXT,
            FOREIGN KEY(league_id) REFERENCES leagues(id) ON DELETE CASCADE,
            FOREIGN KEY(fighter_id) REFERENCES fighters(id) ON DELETE SET NULL,
            FOREIGN KEY(requester_user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(reviewed_by_user_id) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS fighter_honours (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id INTEGER NOT NULL,
            fighter_id INTEGER NOT NULL,
            honour_type TEXT NOT NULL CHECK(honour_type IN ('special_awards','gold_medals','silver_medals','bronze_medals')),
            units INTEGER NOT NULL DEFAULT 1,
            title TEXT,
            notes TEXT,
            awarded_on TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(league_id) REFERENCES leagues(id) ON DELETE CASCADE,
            FOREIGN KEY(fighter_id) REFERENCES fighters(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS training_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            notes TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(league_id, name),
            FOREIGN KEY(league_id) REFERENCES leagues(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS training_group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            training_group_id INTEGER NOT NULL,
            fighter_id INTEGER NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE(training_group_id, fighter_id),
            FOREIGN KEY(training_group_id) REFERENCES training_groups(id) ON DELETE CASCADE,
            FOREIGN KEY(fighter_id) REFERENCES fighters(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_user_id INTEGER,
            league_id INTEGER,
            created_at TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER,
            action TEXT NOT NULL,
            message TEXT NOT NULL,
            before_state TEXT,
            after_state TEXT,
            rollback_type TEXT,
            FOREIGN KEY(actor_user_id) REFERENCES users(id),
            FOREIGN KEY(league_id) REFERENCES leagues(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS team_share_links (
            team_id INTEGER PRIMARY KEY,
            token TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(team_id) REFERENCES fantasy_teams(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS event_banners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id INTEGER,
            event_name TEXT NOT NULL,
            event_date TEXT NOT NULL,
            location TEXT,
            source_url TEXT,
            summary TEXT,
            source_kind TEXT NOT NULL DEFAULT 'manual',
            external_key TEXT,
            headline TEXT,
            subheading TEXT,
            image_url TEXT,
            FOREIGN KEY(league_id) REFERENCES leagues(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS external_cache (
            key TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            refreshed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS seasons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('active','completed')),
            locked INTEGER NOT NULL DEFAULT 0,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            winner_team_id INTEGER,
            winner_team_name TEXT,
            winner_player_user_id INTEGER,
            winner_player_name TEXT,
            final_leaderboard_json TEXT,
            completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS season_team_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_id INTEGER NOT NULL,
            team_id INTEGER,
            rank INTEGER,
            team_name TEXT NOT NULL,
            manager TEXT NOT NULL,
            player_user_id INTEGER,
            player_name TEXT,
            status TEXT NOT NULL,
            points INTEGER NOT NULL,
            cost INTEGER NOT NULL,
            remaining INTEGER NOT NULL,
            member_count INTEGER NOT NULL,
            image_path TEXT,
            image_credit TEXT,
            image_source_url TEXT,
            roster_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(season_id) REFERENCES seasons(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS season_fighter_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_id INTEGER NOT NULL,
            fighter_id INTEGER,
            rank INTEGER,
            name TEXT NOT NULL,
            tier TEXT,
            current_cost INTEGER NOT NULL,
            total_points INTEGER NOT NULL,
            training INTEGER NOT NULL,
            competitions INTEGER NOT NULL,
            support INTEGER NOT NULL,
            gold_medals INTEGER NOT NULL,
            silver_medals INTEGER NOT NULL,
            bronze_medals INTEGER NOT NULL,
            kills INTEGER NOT NULL,
            deaths INTEGER NOT NULL,
            sit_downs INTEGER NOT NULL,
            yellow_cards INTEGER NOT NULL,
            red_cards INTEGER NOT NULL,
            kd_ratio REAL NOT NULL,
            fame_score INTEGER NOT NULL,
            discipline_score INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(season_id) REFERENCES seasons(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS season_cost_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_id INTEGER NOT NULL,
            fighter_id INTEGER NOT NULL,
            fighter_name TEXT NOT NULL,
            old_cost INTEGER NOT NULL,
            new_cost INTEGER NOT NULL,
            pick_count INTEGER NOT NULL,
            team_count INTEGER NOT NULL,
            pick_rate REAL NOT NULL,
            target_pick_rate REAL NOT NULL,
            sensitivity REAL NOT NULL,
            raw_adjustment REAL NOT NULL,
            applied_adjustment REAL NOT NULL,
            clamp_limit REAL NOT NULL,
            round_unit INTEGER NOT NULL,
            min_cost INTEGER NOT NULL,
            max_cost INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(season_id) REFERENCES seasons(id) ON DELETE CASCADE
        );
        """
    )
    now_iso = config["now_iso"]
    conn.execute(
        """
        INSERT INTO leagues(slug,name,club_name,status,description,created_at,updated_at)
        VALUES(?,?,?,'active',?,?,?)
        ON CONFLICT(slug) DO UPDATE SET
            name=excluded.name,
            club_name=excluded.club_name,
            updated_at=excluded.updated_at
        """,
        (
            config["default_league_slug"],
            config["default_league_name"],
            config["default_league_club_name"],
            "Default league migrated from the original single-league Invicta setup.",
            now_iso(),
            now_iso(),
        ),
    )
    default_league_id = conn.execute("SELECT id FROM leagues WHERE slug=?", (config["default_league_slug"],)).fetchone()["id"]
    league_columns = {row["name"] for row in conn.execute("PRAGMA table_info(leagues)")}
    if "logo_url" not in league_columns:
        conn.execute("ALTER TABLE leagues ADD COLUMN logo_url TEXT")
    if "join_code" not in league_columns:
        conn.execute("ALTER TABLE leagues ADD COLUMN join_code TEXT")
    conn.execute(
        """
        UPDATE leagues
        SET join_code=UPPER(SUBSTR(HEX(RANDOMBLOB(4)), 1, 8))
        WHERE join_code IS NULL OR TRIM(join_code)=''
        """
    )
    fighter_columns = {row["name"] for row in conn.execute("PRAGMA table_info(fighters)")}
    if "spreadsheet_id" not in fighter_columns:
        conn.execute("ALTER TABLE fighters ADD COLUMN spreadsheet_id TEXT")
    if "league_id" not in fighter_columns:
        conn.execute("ALTER TABLE fighters ADD COLUMN league_id INTEGER REFERENCES leagues(id) ON DELETE SET NULL")
    if "age" not in fighter_columns:
        conn.execute("ALTER TABLE fighters ADD COLUMN age INTEGER")
    if "active" not in fighter_columns:
        conn.execute("ALTER TABLE fighters ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
    if "start_year" not in fighter_columns:
        conn.execute("ALTER TABLE fighters ADD COLUMN start_year INTEGER")
    if "bio" not in fighter_columns:
        conn.execute("ALTER TABLE fighters ADD COLUMN bio TEXT")
    if "next_season_cost" not in fighter_columns:
        conn.execute("ALTER TABLE fighters ADD COLUMN next_season_cost INTEGER")
        conn.execute("UPDATE fighters SET next_season_cost=current_cost WHERE next_season_cost IS NULL")
    if "hero_quote" not in fighter_columns:
        conn.execute("ALTER TABLE fighters ADD COLUMN hero_quote TEXT")
    if "image_credit" not in fighter_columns:
        conn.execute("ALTER TABLE fighters ADD COLUMN image_credit TEXT")
    if "image_source_url" not in fighter_columns:
        conn.execute("ALTER TABLE fighters ADD COLUMN image_source_url TEXT")
    if "role_or_weapon" not in fighter_columns:
        conn.execute("ALTER TABLE fighters ADD COLUMN role_or_weapon TEXT")
    if "known_for" not in fighter_columns:
        conn.execute("ALTER TABLE fighters ADD COLUMN known_for TEXT")
    if "why_buhurt" not in fighter_columns:
        conn.execute("ALTER TABLE fighters ADD COLUMN why_buhurt TEXT")
    if "joined_year" not in fighter_columns:
        conn.execute("ALTER TABLE fighters ADD COLUMN joined_year INTEGER")
        conn.execute("UPDATE fighters SET joined_year=start_year WHERE joined_year IS NULL AND start_year IS NOT NULL")
    if "fantasy_insight" not in fighter_columns:
        conn.execute("ALTER TABLE fighters ADD COLUMN fantasy_insight TEXT")
    conn.execute("UPDATE fighters SET next_season_cost=current_cost WHERE next_season_cost IS NULL")
    user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    user_table_sql_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    user_table_sql = user_table_sql_row["sql"] if user_table_sql_row else ""
    if "CHECK(role IN ('admin','player'))" in user_table_sql:
        manager_limit_expr = "manager_limit" if "manager_limit" in user_columns else "1"
        league_id_expr = "league_id" if "league_id" in user_columns else "NULL"
        claimed_at_expr = "claimed_at" if "claimed_at" in user_columns else "NULL"
        conn.commit()
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            """
            CREATE TABLE users_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('site_admin','league_admin','player')),
                team_id INTEGER,
                manager_limit INTEGER NOT NULL DEFAULT 1,
                league_id INTEGER,
                claimed_at TEXT,
                FOREIGN KEY(league_id) REFERENCES leagues(id) ON DELETE SET NULL
            )
            """
        )
        conn.execute(
            f"""
            INSERT INTO users_new(id, username, display_name, password_hash, role, team_id, manager_limit, league_id, claimed_at)
            SELECT
                id,
                username,
                display_name,
                password_hash,
                CASE WHEN role='admin' THEN 'site_admin' ELSE role END,
                team_id,
                COALESCE({manager_limit_expr}, 1),
                {league_id_expr},
                {claimed_at_expr}
            FROM users
            """
        )
        conn.execute("DROP TABLE users")
        conn.execute("ALTER TABLE users_new RENAME TO users")
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")
        user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    if "claimed_at" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN claimed_at TEXT")
    if "manager_limit" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN manager_limit INTEGER NOT NULL DEFAULT 1")
    if "league_id" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN league_id INTEGER REFERENCES leagues(id) ON DELETE SET NULL")
    conn.execute("UPDATE users SET role='site_admin' WHERE role='admin'")
    membership_columns = {row["name"] for row in conn.execute("PRAGMA table_info(league_memberships)")}
    if "manager_limit" not in membership_columns:
        conn.execute("ALTER TABLE league_memberships ADD COLUMN manager_limit INTEGER NOT NULL DEFAULT 1")
    if "status" not in membership_columns:
        conn.execute("ALTER TABLE league_memberships ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
    if "joined_at" not in membership_columns:
        conn.execute("ALTER TABLE league_memberships ADD COLUMN joined_at TEXT")
    if "invited_at" not in membership_columns:
        conn.execute("ALTER TABLE league_memberships ADD COLUMN invited_at TEXT")
    if "left_at" not in membership_columns:
        conn.execute("ALTER TABLE league_memberships ADD COLUMN left_at TEXT")
    if "created_at" not in membership_columns:
        conn.execute("ALTER TABLE league_memberships ADD COLUMN created_at TEXT")
    if "updated_at" not in membership_columns:
        conn.execute("ALTER TABLE league_memberships ADD COLUMN updated_at TEXT")
    backfill_league_memberships(now_iso())
    team_columns = {row["name"] for row in conn.execute("PRAGMA table_info(fantasy_teams)")}
    if "player_user_id" not in team_columns:
        conn.execute("ALTER TABLE fantasy_teams ADD COLUMN player_user_id INTEGER")
        conn.execute(
            """
            UPDATE fantasy_teams
            SET player_user_id = (
                SELECT users.id
                FROM users
                WHERE users.team_id = fantasy_teams.id
                  AND users.role = 'player'
                ORDER BY users.id
                LIMIT 1
            )
            WHERE player_user_id IS NULL
            """
        )
    if "league_id" not in team_columns:
        conn.execute("ALTER TABLE fantasy_teams ADD COLUMN league_id INTEGER REFERENCES leagues(id) ON DELETE SET NULL")
    if "image_path" not in team_columns:
        conn.execute("ALTER TABLE fantasy_teams ADD COLUMN image_path TEXT")
    if "image_credit" not in team_columns:
        conn.execute("ALTER TABLE fantasy_teams ADD COLUMN image_credit TEXT")
    if "image_source_url" not in team_columns:
        conn.execute("ALTER TABLE fantasy_teams ADD COLUMN image_source_url TEXT")
    event_result_columns = {row["name"] for row in conn.execute("PRAGMA table_info(event_results)")}
    if "scheduled_event_id" not in event_result_columns:
        conn.execute("ALTER TABLE event_results ADD COLUMN scheduled_event_id INTEGER")
    if "league_id" not in event_result_columns:
        conn.execute("ALTER TABLE event_results ADD COLUMN league_id INTEGER REFERENCES leagues(id) ON DELETE SET NULL")
    if "rounds_fought" not in event_result_columns:
        conn.execute("ALTER TABLE event_results ADD COLUMN rounds_fought INTEGER NOT NULL DEFAULT 0")
    if "special_awards" not in event_result_columns:
        conn.execute("ALTER TABLE event_results ADD COLUMN special_awards INTEGER NOT NULL DEFAULT 0")
    if "assists" not in event_result_columns:
        conn.execute("ALTER TABLE event_results ADD COLUMN assists INTEGER NOT NULL DEFAULT 0")
    if "group_name" not in event_result_columns:
        conn.execute("ALTER TABLE event_results ADD COLUMN group_name TEXT")
    if "entry_status" not in event_result_columns:
        conn.execute("ALTER TABLE event_results ADD COLUMN entry_status TEXT NOT NULL DEFAULT 'draft'")
    if "updated_at" not in event_result_columns:
        conn.execute("ALTER TABLE event_results ADD COLUMN updated_at TEXT")
    event_banner_columns = {row["name"] for row in conn.execute("PRAGMA table_info(event_banners)")}
    event_banner_table_sql_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='event_banners'"
    ).fetchone()
    event_banner_table_sql = event_banner_table_sql_row["sql"] if event_banner_table_sql_row else ""
    if "UNIQUE(event_name, event_date)" in event_banner_table_sql:
        conn.commit()
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            """
            CREATE TABLE event_banners_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                league_id INTEGER,
                event_name TEXT NOT NULL,
                event_date TEXT NOT NULL,
                location TEXT,
                source_url TEXT,
                summary TEXT,
                source_kind TEXT NOT NULL DEFAULT 'manual',
                external_key TEXT,
                headline TEXT,
                subheading TEXT,
                image_url TEXT,
                FOREIGN KEY(league_id) REFERENCES leagues(id) ON DELETE SET NULL
            )
            """
        )
        location_expr = "location" if "location" in event_banner_columns else "NULL"
        source_url_expr = "source_url" if "source_url" in event_banner_columns else "NULL"
        summary_expr = "summary" if "summary" in event_banner_columns else "NULL"
        source_kind_expr = "source_kind" if "source_kind" in event_banner_columns else "'manual'"
        external_key_expr = "external_key" if "external_key" in event_banner_columns else "NULL"
        conn.execute(
            f"""
            INSERT INTO event_banners_new(
                id, league_id, event_name, event_date, location, source_url, summary, source_kind, external_key, headline, subheading, image_url
            )
            SELECT
                id,
                league_id,
                event_name,
                event_date,
                {location_expr},
                {source_url_expr},
                {summary_expr},
                {source_kind_expr},
                {external_key_expr},
                headline,
                subheading,
                image_url
            FROM event_banners
            """
        )
        conn.execute("DROP TABLE event_banners")
        conn.execute("ALTER TABLE event_banners_new RENAME TO event_banners")
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")
        event_banner_columns = {row["name"] for row in conn.execute("PRAGMA table_info(event_banners)")}
    if "league_id" not in event_banner_columns:
        conn.execute("ALTER TABLE event_banners ADD COLUMN league_id INTEGER REFERENCES leagues(id) ON DELETE SET NULL")
    if "location" not in event_banner_columns:
        conn.execute("ALTER TABLE event_banners ADD COLUMN location TEXT")
    if "source_url" not in event_banner_columns:
        conn.execute("ALTER TABLE event_banners ADD COLUMN source_url TEXT")
    if "summary" not in event_banner_columns:
        conn.execute("ALTER TABLE event_banners ADD COLUMN summary TEXT")
    if "source_kind" not in event_banner_columns:
        conn.execute("ALTER TABLE event_banners ADD COLUMN source_kind TEXT NOT NULL DEFAULT 'manual'")
    if "external_key" not in event_banner_columns:
        conn.execute("ALTER TABLE event_banners ADD COLUMN external_key TEXT")
    fighter_import_columns = {row["name"] for row in conn.execute("PRAGMA table_info(fighter_import_totals)")}
    for column_name in config["imported_fighter_stat_keys"]:
        if column_name not in fighter_import_columns:
            conn.execute(f"ALTER TABLE fighter_import_totals ADD COLUMN {column_name} INTEGER NOT NULL DEFAULT 0")
    attendance_columns = {row["name"] for row in conn.execute("PRAGMA table_info(attendance_scores)")}
    if "league_id" not in attendance_columns:
        conn.execute("ALTER TABLE attendance_scores ADD COLUMN league_id INTEGER REFERENCES leagues(id) ON DELETE SET NULL")
    claim_token_columns = {row["name"] for row in conn.execute("PRAGMA table_info(claim_tokens)")}
    if "league_id" not in claim_token_columns:
        conn.execute("ALTER TABLE claim_tokens ADD COLUMN league_id INTEGER REFERENCES leagues(id) ON DELETE SET NULL")
    notification_columns = {row["name"] for row in conn.execute("PRAGMA table_info(notifications)")}
    if "league_id" not in notification_columns:
        conn.execute("ALTER TABLE notifications ADD COLUMN league_id INTEGER REFERENCES leagues(id) ON DELETE SET NULL")
    audit_columns = {row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")}
    if "league_id" not in audit_columns:
        conn.execute("ALTER TABLE audit_logs ADD COLUMN league_id INTEGER REFERENCES leagues(id) ON DELETE SET NULL")
    conn.execute(
        """
        UPDATE event_results
        SET scheduled_event_id = (
            SELECT eb.id
            FROM event_banners eb
            WHERE eb.event_name = event_results.event_name
              AND eb.event_date = event_results.event_date
            ORDER BY eb.id DESC
            LIMIT 1
        )
        WHERE scheduled_event_id IS NULL
        """
    )
    conn.execute("UPDATE fighters SET league_id=? WHERE league_id IS NULL", (default_league_id,))
    conn.execute("UPDATE fantasy_teams SET league_id=? WHERE league_id IS NULL", (default_league_id,))
    conn.execute(
        """
        UPDATE event_banners
        SET league_id = COALESCE(
            league_id,
            (
                SELECT er.league_id
                FROM event_results er
                WHERE er.scheduled_event_id = event_banners.id
                  AND er.league_id IS NOT NULL
                ORDER BY er.id DESC
                LIMIT 1
            ),
            ?
        )
        WHERE league_id IS NULL
        """,
        (default_league_id,),
    )
    conn.execute("UPDATE event_results SET entry_status='complete' WHERE entry_status IS NULL OR entry_status=''")
    conn.execute("UPDATE event_results SET updated_at=? WHERE updated_at IS NULL", (now_iso(),))
    conn.execute("UPDATE event_banners SET source_kind='manual' WHERE source_kind IS NULL OR source_kind=''")
    conn.execute(
        """
        UPDATE users
        SET league_id = COALESCE(
            league_id,
            (
                SELECT ft.league_id
                FROM fantasy_teams ft
                WHERE ft.id = users.team_id
                LIMIT 1
            ),
            ?
        )
        WHERE league_id IS NULL
        """,
        (default_league_id,),
    )
    conn.execute(
        """
        UPDATE event_results
        SET league_id = COALESCE(
            league_id,
            (
                SELECT f.league_id
                FROM fighters f
                WHERE f.id = event_results.fighter_id
                LIMIT 1
            ),
            ?
        )
        WHERE league_id IS NULL
        """,
        (default_league_id,),
    )
    conn.execute(
        """
        UPDATE attendance_scores
        SET league_id = COALESCE(
            league_id,
            (
                SELECT f.league_id
                FROM fighters f
                WHERE f.id = attendance_scores.fighter_id
                LIMIT 1
            ),
            ?
        )
        WHERE league_id IS NULL
        """,
        (default_league_id,),
    )
    conn.execute(
        """
        UPDATE claim_tokens
        SET league_id = COALESCE(
            league_id,
            (
                SELECT u.league_id
                FROM users u
                WHERE u.id = claim_tokens.user_id
                LIMIT 1
            ),
            ?
        )
        WHERE league_id IS NULL
        """,
        (default_league_id,),
    )
    conn.execute("UPDATE notifications SET league_id=? WHERE league_id IS NULL", (default_league_id,))
    for key, value in config["season_cost_defaults"].items():
        conn.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO NOTHING",
            (key, str(value)),
        )
    for key, value in config["public_profile_formula_defaults"].items():
        conn.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO NOTHING",
            (key, str(value)),
        )
    for row in config["rule_default_rows"]:
        conn.execute(
            "INSERT INTO rules(key,label,points,notes) VALUES(?,?,?,?) ON CONFLICT(key) DO NOTHING",
            row,
        )
    conn.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO NOTHING",
        ("public_fighter_scores_visible", config["public_score_visibility_default"]),
    )
    config["migrate_attendance_scores_to_baseline"](conn)
    ensure_indexes(conn)
    existing = conn.execute("SELECT COUNT(*) AS c FROM fighters").fetchone()["c"]
    if existing == 0:
        seed = json.loads(config["seed_path"].read_text(encoding="utf-8"))
        execute_many(conn, "INSERT INTO rules(key,label,points,notes) VALUES(:key,:label,:points,:notes)", seed["rules"])
        execute_many(conn, "INSERT INTO settings(key,value) VALUES(?,?)", [(k, str(v)) for k, v in seed["settings"].items()])
        execute_many(conn, "INSERT INTO ownership_brackets(lower_bound,adjustment,meaning) VALUES(:lower_bound,:adjustment,:meaning)", seed["ownership_brackets"])
        execute_many(
            conn,
            "INSERT INTO fighters(name,tier,height,weight,current_cost,notes,league_id) VALUES(:name,:tier,:height,:weight,:current_cost,:notes,:league_id)",
            [{**fighter, "league_id": default_league_id} for fighter in seed["fighters"]],
        )
        fighter_ids = {r["name"]: r["id"] for r in conn.execute("SELECT id,name FROM fighters")}
        for row in seed["baseline"]:
            fid = fighter_ids.get(row["fighter_name"])
            if fid:
                conn.execute("INSERT INTO baseline_stats(fighter_id,training,support) VALUES(?,?,?)", (fid, row["training"], row["support"]))
        for fighter in seed["fighters"]:
            fid = fighter_ids.get(fighter["name"])
            conn.execute("INSERT OR IGNORE INTO baseline_stats(fighter_id,training,support) VALUES(?,?,?)", (fid, 0, 0))
        for row in seed["events"]:
            fid = fighter_ids.get(row["fighter_name"])
            if fid:
                conn.execute(
                    """
                    INSERT INTO event_results(event_date,event_name,fighter_id,league_id,rounds_fought,special_awards,gold_medals,silver_medals,bronze_medals,kills,assists,deaths,sit_downs,yellow_cards,red_cards)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        row["event_date"],
                        row["event_name"],
                        fid,
                        default_league_id,
                        row.get("rounds_fought", 0),
                        row.get("special_awards", 0),
                        row["gold_medals"],
                        row["silver_medals"],
                        row["bronze_medals"],
                        row["kills"],
                        row.get("assists", 0),
                        row["deaths"],
                        row["sit_downs"],
                        row["yellow_cards"],
                        row["red_cards"],
                    )
                )
        for team in seed["fantasy_teams"]:
            cur = conn.execute(
                "INSERT INTO fantasy_teams(team_name,manager,league_id) VALUES(?,?,?)",
                (team["team_name"], team["manager"], default_league_id),
            )
            team_id = cur.lastrowid
            for slot, fighter_name in enumerate(team["fighters"], start=1):
                fid = fighter_ids.get(fighter_name)
                if fid:
                    conn.execute("INSERT INTO fantasy_team_fighters(team_id,fighter_id,slot) VALUES(?,?,?)", (team_id, fid, slot))
        admin_password = os.environ.get("INV_ADMIN_PASSWORD", "admin123")
        conn.execute(
            "INSERT INTO users(username,display_name,password_hash,role,league_id) VALUES(?,?,?,?,?)",
            ("admin", "Admin", config["generate_password_hash"](admin_password), "site_admin", default_league_id),
        )
        team_rows = conn.execute("SELECT id, manager FROM fantasy_teams").fetchall()
        for team in team_rows:
            username = re.sub(r"[^a-z0-9]+", "_", team["manager"].strip().lower()).strip("_") or f"player_{team['id']}"
            if conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
                username = f"{username}_{team['id']}"
            cur = conn.execute(
                "INSERT INTO users(username,display_name,password_hash,role,team_id,league_id) VALUES(?,?,?,?,?,?)",
                (username, team["manager"], config["generate_password_hash"]("player123"), "player", team["id"], default_league_id),
            )
            conn.execute("UPDATE fantasy_teams SET player_user_id=? WHERE id=?", (cur.lastrowid, team["id"]))
    backfill_league_memberships(now_iso())
    conn.commit()
    config["ensure_active_season"](conn)
    conn.close()
