import os
import json
import secrets
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    abort,
    g,
    has_request_context,
    has_app_context,
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# Shared Exceptions
from exceptions import ValidationError, QuotaExceededError

# Support Modules
from auth_support import (
    current_user,
    memberships_for_user,
    ensure_active_league_membership,
    active_membership_for_user,
    current_user_league_id,
    current_league,
    default_league_id,
    effective_league_id,
    scoped_league_id,
    is_site_admin,
    effective_role_for_user,
    is_league_admin,
    is_admin_user,
    csrf_token,
    protect_post_requests,
    login_required,
    admin_required,
    site_admin_required,
    LeagueScopeManager,
)
from db_support import (
    close_db as close_db_connection,
    ensure_runtime_tables as ensure_runtime_tables_impl,
    get_db,
    init_db as run_init_db,
)
from form_support import (
    attendance_score_form_values,
    fighter_baseline_values,
    fighter_form_values,
    parse_int_field,
    parse_optional_float,
    submitted_baseline,
    submitted_fighter_form,
)
from league_data_support import (
    attendance_score_aggregates as load_attendance_score_aggregates,
    current_cost_map as load_current_cost_map,
    fighter_admin_totals as load_fighter_admin_totals,
    fighter_aggregates as load_fighter_aggregates,
    fighter_import_totals as load_fighter_import_totals,
    fighter_ownership_rates as load_fighter_ownership_rates,
    get_team_selections as load_team_selections,
    leaderboard_rows as load_leaderboard_rows,
    migrate_attendance_scores_to_baseline as migrate_attendance_scores_to_baseline_impl,
    ownership_next_costs as load_ownership_next_costs,
    raw_fighter_stats as load_raw_fighter_stats,
    team_rows as load_team_rows,
)
from ops_support import (
    active_claim_token_for_user,
    active_notifications,
    audit_logs as load_audit_rows,
    create_claim_token,
    create_notification,
    event_result_audit_state,
    event_state,
    get_or_create_share_token,
    latest_event_banner,
    log_audit,
    scheduled_event_rows as load_scheduled_event_rows,
    team_state,
    get_ops_engine,
)
from player_support import (
    parse_int_field_from_value,
    parse_optional_player_user_id,
    parse_optional_team_id,
    player_form_values,
    player_manager_slot_usage,
    player_rows,
    selected_fighter_ids_from_form,
    submitted_player_form,
    team_builder_context,
    team_fighter_ids,
    team_form_values,
    teams_for_player,
    valid_player_user_id,
    valid_team_id,
)
from quota_support import (
    league_quota_summary,
    require_player_capacity,
    require_team_capacity,
)
from public_support import (
    compare_team_payload,
    home_payload as load_home_payload,
    latest_event_results_payload,
    public_event_fighter_display as build_public_event_fighter_display,
)
from scoring_support import (
    apply_public_profile_ratings as build_public_profile_ratings,
    calculate_season_cost_changes,
    event_points as build_event_points,
    float_setting,
    season_cost_settings_from_settings,
    validate_team,
)
from season_support import (
    completed_seasons,
    current_season,
    end_active_season,
    ensure_active_season,
    hall_of_fame_data,
    require_active_season_editable,
    season_lock_state,
    snapshot_team_row,
)
from dataclasses import asdict
from tournament_support import (
    BuhurtCalendarClient,
    BuhurtEvent,
    parse_event_date_range as build_parse_event_date_range,
    fallback_buhurt_uk_tournaments as build_fallback_buhurt_uk_tournaments,
)
from ui_support import (
    apply_collection_filters as build_apply_collection_filters,
    event_summary_text as build_event_summary_text,
    filter_option_rows as build_filter_option_rows,
    public_fighter_affiliation as build_public_fighter_affiliation,
    public_fighter_display as build_public_fighter_display,
    public_fighter_form_label as build_public_fighter_form_label,
    public_fighter_spotlight_label as build_public_fighter_spotlight_label,
    public_top_fighter_label as build_public_top_fighter_label,
    query_text as build_query_text,
    tier_legend_items as build_tier_legend_items,
    tier_theme as build_tier_theme,
    FighterPresenter,
)

import team_support

# Route Registrations
from routes_admin_dashboard import register_admin_dashboard_routes
from routes_admin_events import register_admin_event_routes
from routes_admin_fighters import register_admin_fighter_routes
from routes_admin_leagues import register_admin_league_routes
from routes_admin_league_admins import register_admin_league_admin_routes
from routes_admin_ops import register_admin_ops_routes
from routes_admin_players import register_admin_player_routes
from routes_admin_season_rules import register_admin_season_rule_routes
from routes_admin_teams import register_admin_team_routes
from routes_player import register_player_routes
from routes_public import register_public_routes

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "league.db"
SEED_PATH = BASE_DIR / "data" / "seed.json"
TEAM_UPLOAD_DIR = BASE_DIR / "static" / "uploads" / "teams"
TEAM_UPLOAD_STATIC_PREFIX = "uploads/teams"
DEFAULT_LEAGUE_SLUG = "invicta"
DEFAULT_LEAGUE_NAME = "Invicta Fantasy League"
DEFAULT_LEAGUE_CLUB_NAME = "Invicta"
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
TIER_THEME_ORDER = ["tier-1", "tier-2", "tier-3", "tier-4", "tier-unknown"]
TIER_THEME_MAP = {
    "tier-1": {"class_name": "tier-1", "label": "Tier 1", "legend": "Gold"},
    "tier-2": {"class_name": "tier-2", "label": "Tier 2", "legend": "Silver"},
    "tier-3": {"class_name": "tier-3", "label": "Tier 3", "legend": "Bronze"},
    "tier-4": {"class_name": "tier-4", "label": "Tier 4+", "legend": "Secondary"},
    "tier-unknown": {"class_name": "tier-unknown", "label": "Unknown Tier", "legend": "Neutral"},
}

STAT_KEYS = [
    "training", "competitions", "support", "special_awards", "gold_medals", "silver_medals", "bronze_medals",
    "kills", "assists", "deaths", "sit_downs", "yellow_cards", "red_cards"
]
EVENT_STAT_KEYS = [
    "special_awards", "gold_medals", "silver_medals", "bronze_medals", "kills", "assists", "deaths", "sit_downs", "yellow_cards", "red_cards"
]
FIGHTER_RESULT_EXTRA_KEYS = ["rounds_fought", "special_awards", "assists"]
IMPORTED_FIGHTER_STAT_KEYS = [
    "training",
    "competitions",
    "rounds_fought",
    "support",
    "special_awards",
    "gold_medals",
    "silver_medals",
    "bronze_medals",
    "kills",
    "assists",
    "deaths",
    "sit_downs",
    "yellow_cards",
    "red_cards",
]
PUBLIC_PROFILE_STAT_ORDER = [
    ("glory", "Glory"),
    ("discipline_rating", "Discipline"),
    ("lethality", "Lethality"),
    ("resilience", "Resilience"),
    ("crowd_favourite", "Crowd Favourite"),
    ("synergy", "Synergy"),
]
PUBLIC_PROFILE_FORMULA_DEFAULTS = {
    "glory_competitions_weight": "3",
    "glory_special_awards_weight": "10",
    "glory_gold_weight": "8",
    "glory_silver_weight": "6",
    "glory_bronze_weight": "5",
    "discipline_training_weight": "1",
    "discipline_competitions_weight": "3",
    "discipline_yellow_penalty": "5",
    "discipline_red_penalty": "10",
    "lethality_kd_weight": "1",
    "resilience_rounds_weight": "1",
    "resilience_deaths_penalty": "1",
    "resilience_sit_downs_penalty": "1",
    "crowd_kills_weight": "1",
    "crowd_gold_weight": "1",
    "crowd_silver_weight": "1",
    "crowd_bronze_weight": "1",
    "crowd_special_awards_weight": "1",
    "crowd_ownership_weight": "5",
    "synergy_support_weight": "3",
    "synergy_assists_weight": "3",
    "synergy_competitions_weight": "3",
    "synergy_yellow_penalty": "5",
    "synergy_red_penalty": "10",
}
PUBLIC_PROFILE_FORMULA_GROUPS = [
    {
        "key": "glory",
        "label": "Glory",
        "description": "Rewards achievement and podium success.",
        "fields": [
            ("glory_competitions_weight", "Competitions"),
            ("glory_special_awards_weight", "Special awards"),
            ("glory_gold_weight", "Gold medals"),
            ("glory_silver_weight", "Silver medals"),
            ("glory_bronze_weight", "Bronze medals"),
        ],
    },
    {
        "key": "discipline",
        "label": "Discipline",
        "description": "Rewards training and reliable appearances while penalising cards.",
        "fields": [
            ("discipline_training_weight", "Training"),
            ("discipline_competitions_weight", "Competitions"),
            ("discipline_yellow_penalty", "Yellow-card penalty"),
            ("discipline_red_penalty", "Red-card penalty"),
        ],
    },
    {
        "key": "lethality",
        "label": "Lethality",
        "description": "Uses kill/death efficiency as the headline attacking metric.",
        "fields": [
            ("lethality_kd_weight", "K/D ratio multiplier"),
        ],
    },
    {
        "key": "resilience",
        "label": "Resilience",
        "description": "Rewards staying active in rounds while penalising deaths and sit-downs.",
        "fields": [
            ("resilience_rounds_weight", "Rounds fought"),
            ("resilience_deaths_penalty", "Deaths penalty"),
            ("resilience_sit_downs_penalty", "Sit-down penalty"),
        ],
    },
    {
        "key": "crowd_favourite",
        "label": "Crowd Favourite",
        "description": "Rewards excitement, medals, awards, and fantasy popularity.",
        "fields": [
            ("crowd_kills_weight", "Kills"),
            ("crowd_gold_weight", "Gold medals"),
            ("crowd_silver_weight", "Silver medals"),
            ("crowd_bronze_weight", "Bronze medals"),
            ("crowd_special_awards_weight", "Special awards"),
            ("crowd_ownership_weight", "Ownership multiplier"),
        ],
    },
    {
        "key": "synergy",
        "label": "Synergy",
        "description": "Rewards support play, assists, and repeat appearances while penalising cards.",
        "fields": [
            ("synergy_support_weight", "Support"),
            ("synergy_assists_weight", "Assists"),
            ("synergy_competitions_weight", "Competitions"),
            ("synergy_yellow_penalty", "Yellow-card penalty"),
            ("synergy_red_penalty", "Red-card penalty"),
        ],
    },
]
BUHURT_UK_EVENTS_URL = "https://mcsagb.co.uk/uk-events"
BUHURT_UK_CACHE_KEY = "buhurt_uk_tournaments"
BUHURT_UK_CALENDAR_CACHE_KEY = "buhurt_uk_calendar"
BUHURT_UK_CACHE_HOURS = 12
FALLBACK_BUHURT_UK_TOURNAMENTS = [
    {
        "name": "Leodis Cup",
        "date": "16-17 May 2026",
        "location": "Kirkstall Abbey, Leeds",
        "summary": "Regional buhurt tournament with 5v5 and free-for-all categories.",
        "url": "https://www.buhurtinternational.com/tournament/the-leodis-cup",
    },
    {
        "name": "Tournament of Deeds",
        "date": "27-28 June 2026",
        "location": "Ledbury",
        "summary": "UK buhurt calendar event hosted at ISCA AFC's training ground.",
        "url": "https://www.buhurtinternational.com/tournament/tournament-of-deeds",
    },
    {
        "name": "Severnside Clash",
        "date": "25 July 2026",
        "location": "Gloucester",
        "summary": "Single-day hard-hitting buhurt competition near Gloucester city centre.",
        "url": "https://www.buhurtinternational.com/tournament/severnside-clash",
    },
    {
        "name": "Heritage Shield",
        "date": "3 October 2026",
        "location": "United Kingdom",
        "summary": "Male and female 5v5 plus men's 12v12 competition.",
        "url": "https://www.buhurtinternational.com/tournament/heritage-shield-2026",
    },
]
LANDING_IMAGES = {
    "hero": {
        "url": "https://commons.wikimedia.org/wiki/Special:FilePath/Buhurt_knight_Helmet.jpg",
        "alt": "Close-up of a medieval buhurt helmet",
        "credit": "Ivan Radic",
        "license": "CC BY 2.0",
        "source": "https://commons.wikimedia.org/wiki/File:Buhurt_knight_Helmet.jpg",
    },
    "combat": {
        "url": "https://commons.wikimedia.org/wiki/Special:FilePath/Foot_Combat_close-up.jpg",
        "alt": "Two armored fighters in foot combat",
        "credit": "Pseudopanax",
        "license": "Public domain",
        "source": "https://commons.wikimedia.org/wiki/File:Foot_Combat_close-up.jpg",
    },
}
DEFAULT_SKINS = {
    "fighter": {
        "url": "https://commons.wikimedia.org/wiki/Special:FilePath/Helmet_-_Medieval_Knight_(PSF).png",
        "alt": "Default medieval helmet fighter portrait",
        "credit": "Pearson Scott Foresman",
        "license": "Public domain",
        "source": "https://commons.wikimedia.org/wiki/File:Helmet_-_Medieval_Knight_(PSF).png",
    },
    "team": {
        "url": "https://commons.wikimedia.org/wiki/Special:FilePath/Heraldic_Shield_Argent.svg",
        "alt": "Default heraldic shield team logo",
        "credit": "Gerbrant",
        "license": "Public domain",
        "source": "https://commons.wikimedia.org/wiki/File:Heraldic_Shield_Argent.svg",
    },
}

app = Flask(__name__)
app.secret_key = os.environ.get("INV_FANTASY_SECRET") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=4 * 1024 * 1024,
    SCHEMA_READY=False,
)
CLAIM_TOKEN_HOURS = 72
SEASON_COST_DEFAULTS = {
    "season_pick_rate_target": "0.2",
    "season_cost_sensitivity": "1.0",
    "season_cost_adjustment_cap": "0.2",
    "season_cost_round_unit": "5",
    "season_min_cost": "25",
    "season_max_cost": "250",
}
RULE_DEFAULT_ROWS = [
    ("special_awards", "Special Awards", 10, "Awarded per special award"),
    ("assists", "Assist", 2, "Awarded per competition assist"),
]

PUBLIC_SCORE_VISIBILITY_DEFAULT = "0"


def db():
    return get_db(DB_PATH, ensure_runtime_tables)


def ensure_runtime_tables(conn):
    ensure_runtime_tables_impl(conn)


@app.before_request
def ensure_db_ready():
    if not app.config.get("SCHEMA_READY") or not DB_PATH.exists():
        init_db()
        app.config["SCHEMA_READY"] = True
        return


@app.teardown_appcontext
def close_db(exc):
    close_db_connection()


def init_db():
    run_init_db(
        {
            "db_path": DB_PATH,
            "seed_path": SEED_PATH,
            "season_cost_defaults": SEASON_COST_DEFAULTS,
            "public_profile_formula_defaults": PUBLIC_PROFILE_FORMULA_DEFAULTS,
            "rule_default_rows": RULE_DEFAULT_ROWS,
            "public_score_visibility_default": PUBLIC_SCORE_VISIBILITY_DEFAULT,
            "imported_fighter_stat_keys": IMPORTED_FIGHTER_STAT_KEYS,
            "default_league_slug": DEFAULT_LEAGUE_SLUG,
            "default_league_name": DEFAULT_LEAGUE_NAME,
            "default_league_club_name": DEFAULT_LEAGUE_CLUB_NAME,
            "now_iso": now_iso,
            "migrate_attendance_scores_to_baseline": migrate_attendance_scores_to_baseline,
            "ensure_active_season": ensure_active_season,
            "generate_password_hash": generate_password_hash,
        }
    )


def effective_role_for_user_wrapped(user=None, conn=None):
    return effective_role_for_user(user)


def can_manage_teams_in_active_league(user=None, conn=None):
    if user is None:
        user = current_user()
    if not user or is_site_admin(user):
        return False
    membership = active_membership_for_user(user)
    if not membership or membership["status"] != "active":
        return False
    return int(membership["manager_limit"] or 0) > 0


def league_for_user(user, conn=None):
    if not user:
        return None
    if conn is None:
        conn = db()
    active_league_id = session.get("active_league_id") if has_request_context() else None
    membership = conn.execute(
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
        (user["id"], active_league_id),
    ).fetchone()
    league_id = membership["league_id"] if membership else user["league_id"]
    if not league_id:
        return None
    return conn.execute("SELECT * FROM leagues WHERE id=?", (league_id,)).fetchone()


def generate_unique_join_code(conn):
    while True:
        code = secrets.token_hex(4).upper()
        existing = conn.execute("SELECT 1 FROM leagues WHERE join_code=? LIMIT 1", (code,)).fetchone()
        if not existing:
            return code


def should_show_public_fighter_scores():
    if has_request_context():
        user = current_user()
        if is_site_admin(user):
            return True
        return bool_setting(settings_dict(db()), "public_fighter_scores_visible", default=False)
    return False


@app.context_processor
def inject_user():
    conn = db()
    scope = LeagueScopeManager(conn)
    user = scope.current_user
    season = current_season(conn) or ensure_active_season(conn)
    memberships = (
        conn.execute(
            """
            SELECT lm.*, l.name AS league_name, l.status AS league_status, l.logo_url AS league_logo_url
            FROM league_memberships lm
            JOIN leagues l ON l.id = lm.league_id
            WHERE lm.user_id=?
            ORDER BY
                CASE
                    WHEN lm.status='active' AND lm.league_id=? THEN 0
                    WHEN lm.status='active' THEN 1
                    WHEN lm.status='invited' THEN 2
                    ELSE 3
                END,
                l.name,
                lm.id
            """,
            (user["id"], scope.active_league_id if user else None),
        ).fetchall()
        if user and not scope.is_site_admin
        else []
    )
    can_manage_teams = can_manage_teams_in_active_league(user) if user else False
    return {
        **scope.to_dict(),
        "current_league": scope.current_league,
        "current_role": scope.effective_role,
        "is_platform_admin": scope.is_site_admin,
        "available_memberships": memberships,
        "can_manage_teams": can_manage_teams,
        "csrf_token": csrf_token(),
        "default_skins": DEFAULT_SKINS,
        "tier_theme": tier_theme,
        "tier_legend_items": tier_legend_items(),
        "public_fighter_display": public_fighter_display,
        "show_public_fighter_scores": should_show_public_fighter_scores(),
        "current_season": season,
    }


@app.before_request
def protect_post_requests_filter():
    return protect_post_requests()


@app.before_request
def protect_inactive_league_access():
    user = current_user()
    if not user or is_site_admin(user):
        return None
    endpoint = request.endpoint or ""
    protected = endpoint.startswith("admin_") or endpoint in {"my_team", "player_team_new"}
    if not protected:
        return None
    league = league_for_user(user)
    if league and league["status"] != "active":
        session.clear()
        csrf_token()
        flash("Your league is not currently active. Please contact the site admin.")
        return redirect(url_for("login"))
    return None


def now_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat()


def season_cost_settings(conn):
    settings = settings_dict(conn)
    return season_cost_settings_from_settings(settings, int_setting)


# calculate_season_cost_changes imported directly


def current_user_id():
    user = current_user()
    return user["id"] if user else None


def parse_event_date_range(raw_date):
    return build_parse_event_date_range(raw_date, os_name=os.name)


def strip_html(value):
    return clean_html(value, unescape_fn=None)


def fetch_buhurt_uk_tournaments():
    from urllib.request import Request, urlopen
    return build_fetch_buhurt_uk_tournaments(
        events_url=BUHURT_UK_EVENTS_URL,
        request_cls=Request,
        urlopen_fn=urlopen,
        parse_event_date_range_fn=parse_event_date_range,
        strip_html_fn=strip_html,
    )


def fallback_buhurt_uk_tournaments():
    return build_fallback_buhurt_uk_tournaments(FALLBACK_BUHURT_UK_TOURNAMENTS, parse_event_date_range)


def buhurt_uk_calendar_events(conn):
    client = BuhurtCalendarClient(
        cache_key=BUHURT_UK_CALENDAR_CACHE_KEY,
        cache_hours=BUHURT_UK_CACHE_HOURS,
        events_url=BUHURT_UK_EVENTS_URL,
        fallback_events=FALLBACK_BUHURT_UK_TOURNAMENTS,
    )
    events = client.get_calendar_events(conn, is_testing=app.config.get("TESTING"))
    return [asdict(e) for e in events]


def upcoming_buhurt_uk_tournaments(conn):
    client = BuhurtCalendarClient(
        cache_key=BUHURT_UK_CALENDAR_CACHE_KEY,
        cache_hours=BUHURT_UK_CACHE_HOURS,
        events_url=BUHURT_UK_EVENTS_URL,
        fallback_events=FALLBACK_BUHURT_UK_TOURNAMENTS,
    )
    events = client.get_upcoming_tournaments(conn, limit=6, is_testing=app.config.get("TESTING"))
    return [asdict(e) for e in events]


def rules_dict(conn):
    return request_cached(
        "rules_dict",
        lambda: {r["key"]: r["points"] for r in conn.execute("SELECT key, points FROM rules")},
    )


def settings_dict(conn):
    return request_cached(
        "settings_dict",
        lambda: {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")},
    )


def int_setting(settings, key, default=0):
    try:
        return int(float(settings.get(key, default)))
    except Exception:
        return default


def public_profile_formula_settings(settings):
    resolved = {}
    for key, raw_default in PUBLIC_PROFILE_FORMULA_DEFAULTS.items():
        try:
            resolved[key] = float(settings.get(key, raw_default))
        except Exception:
            resolved[key] = float(raw_default)
    return resolved


def public_profile_formula_groups(settings):
    resolved = public_profile_formula_settings(settings)
    groups = []
    for group in PUBLIC_PROFILE_FORMULA_GROUPS:
        groups.append(
            {
                **group,
                "fields": [
                    {"key": key, "label": label, "value": resolved[key]}
                    for key, label in group["fields"]
                ],
            }
        )
    return groups


def bool_setting(settings, key, default=False):
    return int_setting(settings, key, 1 if default else 0) > 0


def base_cost_for_tier(settings, tier):
    key = tier.lower().replace(" ", "_") + "_cost"
    return int_setting(settings, key, 0)


def request_cached(key, factory):
    if not has_request_context():
        return factory()
    cache = getattr(g, "_computed_cache", None)
    if cache is None:
        cache = {}
        g._computed_cache = cache
    if key not in cache:
        cache[key] = factory()
    return cache[key]


def migrate_attendance_scores_to_baseline(conn):
    return migrate_attendance_scores_to_baseline_impl(conn)


def fighter_aggregates(conn):
    return load_fighter_aggregates(conn, request_cached_fn=request_cached, scoped_league_id_fn=scoped_league_id)


def fighter_ownership_rates(conn):
    return load_fighter_ownership_rates(conn, request_cached_fn=request_cached, scoped_league_id_fn=scoped_league_id)


def fighter_import_totals(conn):
    return load_fighter_import_totals(conn, request_cached_fn=request_cached, scoped_league_id_fn=scoped_league_id)


def apply_public_profile_ratings(rows):
    if has_app_context():
        formula_settings = public_profile_formula_settings(settings_dict(db()))
    else:
        formula_settings = public_profile_formula_settings({})
    return build_public_profile_ratings(
        rows,
        PUBLIC_PROFILE_STAT_ORDER,
        formula_settings,
    )


def attendance_score_aggregates(conn):
    return load_attendance_score_aggregates(conn, request_cached_fn=request_cached, scoped_league_id_fn=scoped_league_id)


def raw_fighter_stats(conn):
    return load_raw_fighter_stats(
        conn,
        request_cached_fn=request_cached,
        fighter_aggregates_fn=fighter_aggregates,
        fighter_import_totals_fn=fighter_import_totals,
        fighter_ownership_rates_fn=fighter_ownership_rates,
        scoped_league_id_fn=scoped_league_id,
        rules_dict_fn=rules_dict,
        tier_theme_fn=tier_theme,
        apply_public_profile_ratings_fn=apply_public_profile_ratings,
        stat_keys=STAT_KEYS,
        fighter_result_extra_keys=FIGHTER_RESULT_EXTRA_KEYS,
    )


def fighter_admin_totals(conn, fighter_id):
    for row in raw_fighter_stats(conn):
        if row["id"] == fighter_id:
            return row
    return None


def current_cost_map(conn):
    return load_current_cost_map(conn, request_cached_fn=request_cached, scoped_league_id_fn=scoped_league_id)


def get_team_selections(conn):
    return load_team_selections(conn, request_cached_fn=request_cached, scoped_league_id_fn=scoped_league_id)


# validate_team imported directly


def ownership_next_costs(conn):
    return load_ownership_next_costs(
        conn,
        request_cached_fn=request_cached,
        current_season_fn=current_season,
        settings_dict_fn=settings_dict,
        current_cost_map_fn=current_cost_map,
        get_team_selections_fn=get_team_selections,
        validate_team_fn=validate_team,
        base_cost_for_tier_fn=base_cost_for_tier,
        scoped_league_id_fn=scoped_league_id,
    )


def query_text(value):
    return build_query_text(value)


def apply_collection_filters(rows, search_fields, filters=None, sort_options=None, search_placeholder="Search", param_prefix=""):
    return build_apply_collection_filters(
        rows,
        query_args=request.args,
        request_path=request.path,
        query_text_fn=query_text,
        urlencode_fn=urlencode,
        search_fields=search_fields,
        filters=filters,
        sort_options=sort_options,
        search_placeholder=search_placeholder,
        param_prefix=param_prefix,
    )


def filter_option_rows(rows, accessor, sort=True):
    return build_filter_option_rows(rows, accessor, query_text, sort=sort)


def tier_theme(tier_value):
    return build_tier_theme(tier_value, TIER_THEME_MAP)


def tier_legend_items():
    return build_tier_legend_items(TIER_THEME_MAP, TIER_THEME_ORDER)


def public_fighter_form_label(rank):
    return build_public_fighter_form_label(rank)


def public_fighter_spotlight_label(fighter, context="leaderboard"):
    return build_public_fighter_spotlight_label(fighter, context=context)


def public_fighter_display(fighter, context="leaderboard"):
    return FighterPresenter(fighter, PUBLIC_PROFILE_STAT_ORDER).to_display_dict(context=context)


def public_top_fighter_label(rank):
    return build_public_top_fighter_label(rank, public_fighter_spotlight_label)


def public_fighter_affiliation(fighter):
    return build_public_fighter_affiliation(fighter)


def event_summary_text(event, top_fighters, best_team):
    return build_event_summary_text(event, top_fighters, best_team)


def public_event_fighter_display(fighter):
    return build_public_event_fighter_display(fighter, public_fighter_display, public_fighter_spotlight_label)


def home_payload(conn):
    return load_home_payload(conn, LANDING_IMAGES)


def sync_calendar_event_banners(conn):
    calendar_events = buhurt_uk_calendar_events(conn)
    client = BuhurtCalendarClient(
        cache_key=BUHURT_UK_CALENDAR_CACHE_KEY,
        cache_hours=BUHURT_UK_CACHE_HOURS,
        events_url=BUHURT_UK_EVENTS_URL,
        fallback_events=FALLBACK_BUHURT_UK_TOURNAMENTS,
    )
    events = [BuhurtEvent(**e) for e in calendar_events]
    active_leagues = conn.execute("SELECT id FROM leagues WHERE status='active'").fetchall()
    return client.sync_banners(conn, events, active_leagues=active_leagues)


def save_team(team_id=None, forced_player_user_id=None):
    return team_support.save_team(db(), team_id, forced_player_user_id)


def scheduled_event_rows(conn):
    return load_scheduled_event_rows(conn, now_iso()[:10])


def leaderboard_rows(conn):
    return load_leaderboard_rows(
        conn,
        request_cached_fn=request_cached,
        settings_dict_fn=settings_dict,
        ownership_next_costs_fn=ownership_next_costs,
        raw_fighter_stats_fn=raw_fighter_stats,
    )


def team_rows(conn):
    return load_team_rows(
        conn,
        request_cached_fn=request_cached,
        settings_dict_fn=settings_dict,
        rules_dict_fn=rules_dict,
        leaderboard_rows_fn=leaderboard_rows,
        get_team_selections_fn=get_team_selections,
        validate_team_fn=validate_team,
        event_points_fn=event_points,
    )


def event_points(row, rules):
    return build_event_points(row, rules, EVENT_STAT_KEYS)


register_admin_dashboard_routes(
    app,
    {
        "admin_required": site_admin_required,
        "current_season": current_season,
        "db": db,
        "ensure_active_season": ensure_active_season,
        "request": request,
        "render_template": render_template,
    },
)

register_admin_league_routes(
    app,
    {
        "ValidationError": ValidationError,
        "abort": abort,
        "admin_required": admin_required,
        "db": db,
        "effective_league_id": effective_league_id,
        "ensure_active_league_membership": ensure_active_league_membership,
        "flash": flash,
        "generate_unique_join_code": generate_unique_join_code,
        "is_site_admin": is_site_admin,
        "log_audit": log_audit,
        "redirect": redirect,
        "render_template": render_template,
        "request": request,
        "site_admin_required": site_admin_required,
        "url_for": url_for,
        "current_user": current_user,
    },
)

register_admin_league_admin_routes(
    app,
    {
        "ValidationError": ValidationError,
        "abort": abort,
        "admin_required": site_admin_required,
        "db": db,
        "flash": flash,
        "generate_password_hash": generate_password_hash,
        "log_audit": log_audit,
        "redirect": redirect,
        "render_template": render_template,
        "request": request,
        "url_for": url_for,
    },
)

register_admin_fighter_routes(
    app,
    {
        "ValidationError": ValidationError,
        "abort": abort,
        "admin_required": admin_required,
        "apply_collection_filters": apply_collection_filters,
        "attendance_score_form_values": attendance_score_form_values,
        "current_season": current_season,
        "current_user": current_user,
        "db": db,
        "effective_league_id": effective_league_id,
        "ensure_active_season": ensure_active_season,
        "fighter_admin_totals": fighter_admin_totals,
        "fighter_baseline_values": fighter_baseline_values,
        "fighter_form_values": fighter_form_values,
        "flash": flash,
        "is_site_admin": is_site_admin,
        "leaderboard_rows": leaderboard_rows,
        "log_audit": log_audit,
        "redirect": redirect,
        "render_template": render_template,
        "request": request,
        "require_active_season_editable": require_active_season_editable,
        "scoped_league_id": scoped_league_id,
        "submitted_baseline": submitted_baseline,
        "submitted_fighter_form": submitted_fighter_form,
        "url_for": url_for,
    },
)

register_admin_event_routes(
    app,
    {
        "ValidationError": ValidationError,
        "abort": abort,
        "admin_required": admin_required,
        "apply_collection_filters": apply_collection_filters,
        "create_notification": create_notification,
        "current_user": current_user,
        "db": db,
        "effective_league_id": effective_league_id,
        "event_points": event_points,
        "event_result_audit_state": event_result_audit_state,
        "flash": flash,
        "is_site_admin": is_site_admin,
        "log_audit": log_audit,
        "now_iso": now_iso,
        "parse_int_field": parse_int_field,
        "redirect": redirect,
        "render_template": render_template,
        "request": request,
        "require_active_season_editable": require_active_season_editable,
        "rules_dict": rules_dict,
        "scoped_league_id": scoped_league_id,
        "scheduled_event_rows": scheduled_event_rows,
        "sync_calendar_event_banners": sync_calendar_event_banners,
        "url_for": url_for,
    },
)

register_admin_player_routes(
    app,
    {
        "ValidationError": ValidationError,
        "abort": abort,
        "active_claim_token_for_user": active_claim_token_for_user,
        "admin_required": admin_required,
        "apply_collection_filters": apply_collection_filters,
        "create_claim_token": create_claim_token,
        "create_notification": create_notification,
        "current_user": current_user,
        "db": db,
        "ensure_active_league_membership": ensure_active_league_membership,
        "effective_league_id": effective_league_id,
        "flash": flash,
        "league_quota_summary": league_quota_summary,
        "generate_password_hash": generate_password_hash,
        "is_site_admin": is_site_admin,
        "log_audit": log_audit,
        "now_iso": now_iso,
        "player_form_values": player_form_values,
        "player_rows": player_rows,
        "redirect": redirect,
        "require_player_capacity": require_player_capacity,
        "render_template": render_template,
        "request": request,
        "scoped_league_id": scoped_league_id,
        "site_admin_required": site_admin_required,
        "submitted_player_form": submitted_player_form,
        "teams_for_player": teams_for_player,
        "url_for": url_for,
    },
)

register_public_routes(
    app,
    {
        "FIGHTER_RESULT_EXTRA_KEYS": FIGHTER_RESULT_EXTRA_KEYS,
        "STAT_KEYS": STAT_KEYS,
        "abort": abort,
        "apply_collection_filters": apply_collection_filters,
        "compare_team_payload": compare_team_payload,
        "current_user": current_user,
        "db": db,
        "event_points": event_points,
        "filter_option_rows": filter_option_rows,
        "get_or_create_share_token": get_or_create_share_token,
        "hall_of_fame_data": hall_of_fame_data,
        "home_payload": home_payload,
        "latest_event_results_payload": latest_event_results_payload,
        "leaderboard_rows": leaderboard_rows,
        "login_required": login_required,
        "public_fighter_affiliation": public_fighter_affiliation,
        "public_fighter_display": public_fighter_display,
        "public_profile_formula_groups": public_profile_formula_groups,
        "public_top_fighter_label": public_top_fighter_label,
        "redirect": redirect,
        "render_template": render_template,
        "request": request,
        "rules_dict": rules_dict,
        "scoped_league_id": scoped_league_id,
        "settings_dict": settings_dict,
        "team_rows": team_rows,
        "url_for": url_for,
    },
)

register_admin_ops_routes(
    app,
    {
        "abort": abort,
        "admin_required": site_admin_required,
        "apply_collection_filters": apply_collection_filters,
        "audit_rows": load_audit_rows,
        "create_notification": create_notification,
        "db": db,
        "effective_league_id": effective_league_id,
        "flash": flash,
        "json": json,
        "log_audit": log_audit,
        "redirect": redirect,
        "render_template": render_template,
        "request": request,
        "url_for": url_for,
        "get_ops_engine": get_ops_engine,
    },
)

register_admin_season_rule_routes(
    app,
    {
        "ValidationError": ValidationError,
        "SEASON_COST_DEFAULTS": SEASON_COST_DEFAULTS,
        "abort": abort,
        "admin_required": site_admin_required,
        "apply_collection_filters": apply_collection_filters,
        "bool_setting": bool_setting,
        "calculate_season_cost_changes": calculate_season_cost_changes,
        "create_notification": create_notification,
        "current_season": current_season,
        "db": db,
        "end_active_season": end_active_season,
        "ensure_active_season": ensure_active_season,
        "flash": flash,
        "int_setting": int_setting,
        "leaderboard_rows": leaderboard_rows,
        "log_audit": log_audit,
        "parse_int_field": parse_int_field,
        "parse_optional_float": parse_optional_float,
        "public_profile_formula_defaults": PUBLIC_PROFILE_FORMULA_DEFAULTS,
        "public_profile_formula_groups": public_profile_formula_groups,
        "redirect": redirect,
        "render_template": render_template,
        "request": request,
        "require_active_season_editable": require_active_season_editable,
        "rules_dict": rules_dict,
        "season_cost_settings": season_cost_settings,
        "settings_dict": settings_dict,
        "team_rows": team_rows,
        "url_for": url_for,
    },
)

register_admin_team_routes(
    app,
    {
        "ValidationError": ValidationError,
        "abort": abort,
        "admin_required": admin_required,
        "apply_collection_filters": apply_collection_filters,
        "filter_option_rows": filter_option_rows,
        "render_template": render_template,
        "request": request,
        "flash": flash,
        "redirect": redirect,
        "url_for": url_for,
        "parse_int_field_from_value": parse_int_field_from_value,
        "scoped_league_id": scoped_league_id,
        "league_quota_summary": league_quota_summary,
        "is_site_admin": is_site_admin,
        "current_user": current_user,
        "db": db,
        "team_rows": team_rows,
    },
)

register_player_routes(
    app,
    {
        "ValidationError": ValidationError,
        "abort": abort,
        "admin_dashboard_endpoint": "admin_dashboard",
        "admin_home_endpoint": "admin_my_league",
        "admin_team_new_endpoint": "admin_team_new",
        "apply_collection_filters": apply_collection_filters,
        "check_password_hash": check_password_hash,
        "can_manage_teams_in_active_league": can_manage_teams_in_active_league,
        "create_notification": create_notification,
        "csrf_token": csrf_token,
        "current_user": current_user,
        "db": db,
        "ensure_active_league_membership": ensure_active_league_membership,
        "flash": flash,
        "generate_password_hash": generate_password_hash,
        "league_for_user": league_for_user,
        "home_payload": home_payload,
        "is_admin_user": is_admin_user,
        "is_site_admin": is_site_admin,
        "log_audit": log_audit,
        "login_required": login_required,
        "now_iso": now_iso,
        "parse_int_field_from_value": parse_int_field_from_value,
        "player_manager_slot_usage": player_manager_slot_usage,
        "redirect": redirect,
        "render_template": render_template,
        "require_player_capacity": require_player_capacity,
        "request": request,
        "save_team": save_team,
        "session": session,
        "team_builder_context": team_builder_context,
        "team_detail_endpoint": "team_detail",
        "team_rows": team_rows,
        "teams_endpoint": "teams",
        "teams_for_player": teams_for_player,
        "get_ops_engine": get_ops_engine,
        "url_for": url_for,
    },
)

if __name__ == "__main__":
    init_db()
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
