import sqlite3
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from src.exceptions import ValidationError
from src.support import scoring as scoring_support
from src.support.ui import tier_theme

# =====================================================================
# Constants & Defaults
# =====================================================================

STAT_KEYS = [
    "training", "competitions", "support", "special_awards", "gold_medals", "silver_medals", "bronze_medals",
    "kills", "assists", "deaths", "sit_downs", "yellow_cards", "red_cards"
]

EVENT_STAT_KEYS = [
    "special_awards", "gold_medals", "silver_medals", "bronze_medals", "kills", "assists", "deaths", "sit_downs", "yellow_cards", "red_cards"
]

FIGHTER_RESULT_EXTRA_KEYS = ["rounds_fought", "special_awards", "assists"]

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

TIER_THEME_ORDER = ["tier-1", "tier-2", "tier-3", "tier-4", "tier-unknown"]
TIER_THEME_MAP = {
    "tier-1": {"class_name": "tier-1", "label": "Tier 1", "legend": "Gold"},
    "tier-2": {"class_name": "tier-2", "label": "Tier 2", "legend": "Silver"},
    "tier-3": {"class_name": "tier-3", "label": "Tier 3", "legend": "Bronze"},
    "tier-4": {"class_name": "tier-4", "label": "Tier 4+", "legend": "Secondary"},
    "tier-unknown": {"class_name": "tier-unknown", "label": "Unknown Tier", "legend": "Neutral"},
}

TEAM_TRAIT_FIELDS = [
    ("glory", "Glory"),
    ("discipline_rating", "Discipline"),
    ("lethality", "Lethality"),
    ("resilience", "Resilience"),
    ("crowd_favourite", "Crowd Favourite"),
    ("synergy", "Synergy"),
]


# =====================================================================
# Domain Data Containers
# =====================================================================

@dataclass(frozen=True)
class FighterRanked:
    fighter_id: int
    name: str
    tier: str
    rank: int
    total_points: int
    current_cost: int
    next_season_cost: int
    overall_rating: float
    glory: int
    discipline: int
    lethality: int
    resilience: int
    crowd_favourite: int
    synergy: int
    competitions: int
    rounds_fought: int
    kills: int
    deaths: int
    assists: int
    gold_medals: int
    silver_medals: int
    bronze_medals: int
    special_awards: int
    training: int
    support: int
    yellow_cards: int
    red_cards: int
    sit_downs: int
    ownership_percent: float
    tier_theme: Dict[str, str] = field(default_factory=dict)
    league_id: Optional[int] = None
    profile_fields: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RosterValidation:
    status: str
    member_count: int
    cost: int
    remaining_budget: int
    reasons: List[str]


@dataclass(frozen=True)
class TeamStanding:
    team_id: int
    team_name: str
    manager: str
    player_user_id: Optional[int]
    player_name: Optional[str]
    image_path: Optional[str]
    image_credit: Optional[str]
    image_source_url: Optional[str]
    points: int
    rank: Optional[int]
    status: str
    fighters: List[FighterRanked]
    trait_totals: List[Dict[str, Any]]
    event_history: List[Dict[str, Any]]
    league_id: int


# =====================================================================
# Core Roster & Rankings Engine
# =====================================================================

class RosterRankingsEngine:

    @staticmethod
    def _calculate_next_season_costs(conn: sqlite3.Connection, league_id: Optional[int], settings: Dict[str, Any]) -> Dict[int, int]:
        season = conn.execute(
            """
            SELECT status
            FROM seasons
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        
        if season and season["status"] == "completed":
            return {
                row["id"]: int(row["next_season_cost"] if row["next_season_cost"] is not None else row["current_cost"])
                for row in conn.execute(
                    "SELECT id,current_cost,next_season_cost FROM fighters WHERE (? IS NULL OR league_id=?)",
                    (league_id, league_id),
                )
            }
            
        current_costs = {
            row["id"]: int(row["current_cost"] or 0)
            for row in conn.execute(
                "SELECT id, current_cost FROM fighters WHERE (? IS NULL OR league_id=?)",
                (league_id, league_id),
            )
        }
        
        teams = conn.execute(
            """
            SELECT * FROM fantasy_teams
            WHERE (? IS NULL OR league_id=?)
            """,
            (league_id, league_id),
        ).fetchall()
        
        selected = {}
        if teams:
            team_ids = [t["id"] for t in teams]
            placeholders = ",".join("?" for _ in team_ids)
            rows = conn.execute(
                f"""
                SELECT ftf.team_id, f.id, f.current_cost
                FROM fantasy_team_fighters ftf
                JOIN fighters f ON f.id = ftf.fighter_id
                WHERE ftf.team_id IN ({placeholders})
                """ ,
                team_ids,
            ).fetchall()
            for row in rows:
                selected.setdefault(row["team_id"], []).append({"id": row["id"]})
                
        valid_teams = []
        for team in teams:
            roster = selected.get(team["id"], [])
            result = scoring_support.validate_team(team, roster, current_costs, settings)
            if result["status"] == "VALID":
                valid_teams.append(team)
                
        total_valid = max(1, len(valid_teams))
        
        owned_counts = {}
        for team in valid_teams:
            for fighter in selected.get(team["id"], []):
                owned_counts[fighter["id"]] = owned_counts.get(fighter["id"], 0) + 1
                
        brackets = conn.execute("SELECT lower_bound, adjustment FROM ownership_brackets ORDER BY lower_bound").fetchall()
        
        out = {}
        fighters = conn.execute(
            "SELECT id, tier, current_cost FROM fighters WHERE (? IS NULL OR league_id=?)",
            (league_id, league_id),
        ).fetchall()
        
        for fighter in fighters:
            fid = fighter["id"]
            pct = owned_counts.get(fid, 0) / total_valid
            adjustment = 0
            for bracket in brackets:
                if pct >= float(bracket["lower_bound"]):
                    adjustment = int(bracket["adjustment"])
            
            tier = fighter["tier"] or ""
            key = tier.lower().replace(" ", "_") + "_cost"
            try:
                base_cost = int(float(settings.get(key, 0)))
            except (ValueError, TypeError):
                base_cost = 0
            
            out[fid] = base_cost + adjustment
            
        return out

    @staticmethod
    def get_fighter_leaderboard(conn: sqlite3.Connection, league_id: Optional[int]) -> List[FighterRanked]:
        # 1. Fetch raw rules and settings
        rules = {r["key"]: r["points"] for r in conn.execute("SELECT key, points FROM rules")}
        db_settings = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}
        
        formula_settings = {}
        for key, val in PUBLIC_PROFILE_FORMULA_DEFAULTS.items():
            try:
                formula_settings[key] = float(db_settings.get(key, val))
            except Exception:
                formula_settings[key] = float(val)

        next_costs_map = RosterRankingsEngine._calculate_next_season_costs(conn, league_id, db_settings)

        # 2. Fetch raw fighters
        fighters = conn.execute(
            """
            SELECT f.*, COALESCE(b.training,0) AS training, COALESCE(b.support,0) AS support
            FROM fighters f
            LEFT JOIN baseline_stats b ON b.fighter_id = f.id
            WHERE (? IS NULL OR f.league_id=?)
            ORDER BY f.tier, f.name
            """,
            (league_id, league_id),
        ).fetchall()

        # 3. Query aggregates from event_results
        rows = conn.execute(
            """
            SELECT fighter_id,
                   COUNT(*) AS competitions,
                   SUM(rounds_fought) AS rounds_fought,
                   SUM(special_awards) AS special_awards,
                   SUM(gold_medals) AS gold_medals,
                   SUM(silver_medals) AS silver_medals,
                   SUM(bronze_medals) AS bronze_medals,
                   SUM(kills) AS kills,
                   SUM(assists) AS assists,
                   SUM(deaths) AS deaths,
                   SUM(sit_downs) AS sit_downs,
                   SUM(yellow_cards) AS yellow_cards,
                   SUM(red_cards) AS red_cards
            FROM event_results
            WHERE (? IS NULL OR league_id=?)
            GROUP BY fighter_id
            """,
            (league_id, league_id),
        ).fetchall()
        aggs = {row["fighter_id"]: dict(row) for row in rows}

        # 4. Query aggregates from fighter_honours
        honour_rows = conn.execute(
            """
            SELECT
                fighter_id,
                SUM(CASE WHEN honour_type='special_awards' THEN units ELSE 0 END) AS special_awards,
                SUM(CASE WHEN honour_type='gold_medals' THEN units ELSE 0 END) AS gold_medals,
                SUM(CASE WHEN honour_type='silver_medals' THEN units ELSE 0 END) AS silver_medals,
                SUM(CASE WHEN honour_type='bronze_medals' THEN units ELSE 0 END) AS bronze_medals
            FROM fighter_honours
            WHERE (? IS NULL OR league_id=?)
            GROUP BY fighter_id
            """,
            (league_id, league_id),
        ).fetchall()
        for row in honour_rows:
            aggregate = aggs.setdefault(
                row["fighter_id"],
                {
                    "fighter_id": row["fighter_id"],
                    "competitions": 0,
                    "rounds_fought": 0,
                    "special_awards": 0,
                    "gold_medals": 0,
                    "silver_medals": 0,
                    "bronze_medals": 0,
                    "kills": 0,
                    "assists": 0,
                    "deaths": 0,
                    "sit_downs": 0,
                    "yellow_cards": 0,
                    "red_cards": 0,
                },
            )
            for key in ("special_awards", "gold_medals", "silver_medals", "bronze_medals"):
                aggregate[key] = int(aggregate.get(key) or 0) + int(row[key] or 0)

        # 5. Query import totals
        rows = conn.execute(
            """
            SELECT fit.*
            FROM fighter_import_totals fit
            JOIN fighters f ON f.id = fit.fighter_id
            WHERE (? IS NULL OR f.league_id=?)
            """,
            (league_id, league_id),
        ).fetchall()
        imported_totals = {row["fighter_id"]: dict(row) for row in rows}

        # 6. Query team counts for ownership rates
        teams = conn.execute(
            "SELECT id FROM fantasy_teams WHERE (? IS NULL OR league_id=?)",
            (league_id, league_id),
        ).fetchall()
        total_teams = max(1, len(teams))
        counts = {}
        for row in conn.execute(
            """
            SELECT ftf.fighter_id
            FROM fantasy_team_fighters ftf
            JOIN fantasy_teams ft ON ft.id = ftf.team_id
            WHERE (? IS NULL OR ft.league_id=?)
            """,
            (league_id, league_id),
        ):
            counts[row["fighter_id"]] = counts.get(row["fighter_id"], 0) + 1
        ownership_rates = {fid: counts[fid] / total_teams for fid in counts}

        # 7. Merge statistics and calculate raw points
        stats_rows = []
        for fighter in fighters:
            row = dict(fighter)
            fid = fighter["id"]
            agg = aggs.get(fid, {})
            imported = imported_totals.get(fid, {})
            
            for key in STAT_KEYS:
                if imported and key in imported:
                    row[key] = int(imported.get(key) or 0)
                elif key in ("training", "support"):
                    row[key] = int(row.get(key) or 0)
                else:
                    row[key] = int(agg.get(key) or 0)

            for key in FIGHTER_RESULT_EXTRA_KEYS:
                if imported and key in imported:
                    row[key] = int(imported.get(key) or 0)
                else:
                    row[key] = int(agg.get(key) or 0)

            row["ownership_percent"] = float(imported.get("ownership_percent", ownership_rates.get(fid, 0)) or 0)
            row["total_points"] = sum(row[k] * rules.get(k, 0) for k in STAT_KEYS)
            row["discipline_score"] = row["training"] + row["competitions"] + row["support"] - row["sit_downs"] - row["yellow_cards"] - row["red_cards"]
            row["kd_ratio"] = row["kills"] / max(1, row["deaths"])
            row["fame_score"] = row["gold_medals"] * 3 + row["silver_medals"] * 2 + row["bronze_medals"] + row["competitions"]
            row["tier_theme"] = tier_theme(row.get("tier"), TIER_THEME_MAP)
            stats_rows.append(row)

        # 8. Normalize metrics to 0-100 ratings
        scoring_support.apply_public_profile_ratings(stats_rows, PUBLIC_PROFILE_STAT_ORDER, formula_settings)

        # 9. Sort by overall rating, total points, and name
        stats_rows.sort(key=lambda r: (-r["overall_rating"], -r["total_points"], r["name"]))
        
        # 10. Map to FighterRanked dataclass
        leaderboard = []
        for index, r in enumerate(stats_rows, start=1):
            next_cost = next_costs_map.get(r["id"], r["current_cost"])
                
            leaderboard.append(
                FighterRanked(
                    fighter_id=r["id"],
                    name=r["name"],
                    tier=r["tier"],
                    rank=index,
                    total_points=r["total_points"],
                    current_cost=r["current_cost"],
                    next_season_cost=next_cost,
                    overall_rating=r["overall_rating"],
                    glory=r["glory"],
                    discipline=r["discipline_rating"],
                    lethality=r["lethality"],
                    resilience=r["resilience"],
                    crowd_favourite=r["crowd_favourite"],
                    synergy=r["synergy"],
                    competitions=r["competitions"],
                    rounds_fought=r["rounds_fought"],
                    kills=r["kills"],
                    deaths=r["deaths"],
                    assists=r["assists"],
                    gold_medals=r["gold_medals"],
                    silver_medals=r["silver_medals"],
                    bronze_medals=r["bronze_medals"],
                    special_awards=r["special_awards"],
                    training=r["training"],
                    support=r["support"],
                    yellow_cards=r["yellow_cards"],
                    red_cards=r["red_cards"],
                    sit_downs=r["sit_downs"],
                    ownership_percent=r["ownership_percent"],
                    tier_theme=r["tier_theme"],
                    league_id=r.get("league_id"),
                    profile_fields=dict(r)
                )
            )
        return leaderboard

    @staticmethod
    def get_team_standings(conn: sqlite3.Connection, league_id: Optional[int]) -> List[TeamStanding]:
        # 1. Fetch rankings and load details
        leaderboard = RosterRankingsEngine.get_fighter_leaderboard(conn, league_id)
        leaderboard_by_id = {f.fighter_id: f for f in leaderboard}
        
        # Determine pricing rules based on settings
        settings = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings").fetchall()}
        use_next = settings.get("cost_mode") == "Next Season"
        costs = {f.fighter_id: (f.next_season_cost if use_next else f.current_cost) for f in leaderboard}
        points_by_fighter = {f.fighter_id: f.total_points for f in leaderboard}

        # 2. Fetch all fantasy teams in league
        teams = conn.execute(
            """
            SELECT ft.*, u.display_name AS player_name, u.username AS player_username
            FROM fantasy_teams ft
            LEFT JOIN users u ON u.id = ft.player_user_id
            WHERE (? IS NULL OR ft.league_id=?)
            ORDER BY ft.team_name
            """,
            (league_id, league_id),
        ).fetchall()

        # 3. Fetch all team rosters
        selected = {team["id"]: [] for team in teams}
        if teams:
            rows = conn.execute(
                """
                SELECT ftf.team_id, ftf.slot, f.*
                FROM fantasy_team_fighters ftf
                JOIN fantasy_teams ft ON ft.id = ftf.team_id
                JOIN fighters f ON f.id = ftf.fighter_id
                WHERE (? IS NULL OR ft.league_id=?)
                ORDER BY ftf.team_id, ftf.slot
                """,
                (league_id, league_id),
            ).fetchall()
            for row in rows:
                selected.setdefault(row["team_id"], []).append(row)

        # 4. Rules map for event point evaluations
        rules = {r["key"]: r["points"] for r in conn.execute("SELECT key, points FROM rules").fetchall()}

        standings = []
        for team in teams:
            team_id = team["id"]
            team_fighters = []
            
            # Enrich roster fighters
            for f in selected[team_id]:
                fid = f["id"]
                ranked_data = leaderboard_by_id.get(fid)
                if ranked_data:
                    team_fighters.append(ranked_data)
                else:
                    # Fallback if not found on leaderboard
                    team_fighters.append(
                        FighterRanked(
                            fighter_id=fid,
                            name=f["name"],
                            tier=f["tier"],
                            rank=999,
                            total_points=0,
                            current_cost=f["current_cost"],
                            next_season_cost=f["current_cost"],
                            overall_rating=0.0,
                            glory=0, discipline=0, lethality=0, resilience=0, crowd_favourite=0, synergy=0,
                            competitions=0, rounds_fought=0, kills=0, deaths=0, assists=0,
                            gold_medals=0, silver_medals=0, bronze_medals=0, special_awards=0,
                            training=0, support=0, yellow_cards=0, red_cards=0, sit_downs=0, ownership_percent=0.0,
                            league_id=f.get("league_id"),
                            profile_fields=dict(f)
                        )
                    )

            # Validate team roster
            validation = scoring_support.validate_team(
                team, 
                [{"id": f.fighter_id} for f in team_fighters], 
                costs, 
                settings, 
                points_by_fighter
            )

            # Trait totals
            trait_totals = [
                {
                    "key": key,
                    "label": label,
                    "value": sum(getattr(f, key, 0) for f in team_fighters),
                }
                for key, label in TEAM_TRAIT_FIELDS
            ]

            # Roster event point contribution history
            event_history = []
            fighter_ids = [f.fighter_id for f in team_fighters]
            if fighter_ids:
                placeholders = ",".join("?" for _ in fighter_ids)
                event_rows = conn.execute(
                    f"""
                    SELECT event_date, event_name, fighter_id, rounds_fought, special_awards, gold_medals, silver_medals, bronze_medals,
                           kills, assists, deaths, sit_downs, yellow_cards, red_cards
                    FROM event_results
                    WHERE fighter_id IN ({placeholders})
                      AND (? IS NULL OR league_id=?)
                    ORDER BY event_date DESC, event_name DESC, id DESC
                    """,
                    (*fighter_ids, team["league_id"], team["league_id"]),
                ).fetchall()
                
                event_map = {}
                for event_row in event_rows:
                    key = (event_row["event_date"], event_row["event_name"])
                    bucket = event_map.setdefault(
                        key,
                        {
                            "event_date": event_row["event_date"],
                            "event_name": event_row["event_name"],
                            "fighters": [],
                            "event_points": 0,
                        },
                    )
                    fighter_pts = sum(int(event_row[k] or 0) * rules.get(k, 0) for k in EVENT_STAT_KEYS)
                    ranked_f = leaderboard_by_id.get(event_row["fighter_id"])
                    
                    bucket["event_points"] += fighter_pts
                    bucket["fighters"].append(
                        {
                            "fighter_id": event_row["fighter_id"],
                            "fighter_name": ranked_f.name if ranked_f else "Unknown Fighter",
                            "event_points": fighter_pts,
                        }
                    )
                event_history = list(event_map.values())

            standings.append(
                TeamStanding(
                    team_id=team_id,
                    team_name=team["team_name"],
                    manager=team["manager"],
                    player_user_id=team["player_user_id"],
                    player_name=team["player_name"],
                    image_path=team["image_path"],
                    image_credit=team["image_credit"],
                    image_source_url=team["image_source_url"],
                    points=validation["points"],
                    rank=None, # Assigned post-sorting
                    status=validation["status"],
                    fighters=team_fighters,
                    trait_totals=trait_totals,
                    event_history=event_history,
                    league_id=team["league_id"]
                )
            )

        # Sort VALID teams by points descending, then name A-Z. Pushes INVALID to bottom.
        valid_sorted = sorted([t for t in standings if t.status == "VALID"], key=lambda t: (-t.points, t.team_name))
        
        ranks = {t.team_id: idx for idx, t in enumerate(valid_sorted, start=1)}
        
        ranked_standings = []
        for t in standings:
            # Reconstruct with rank
            rank_val = ranks.get(t.team_id)
            ranked_standings.append(
                TeamStanding(
                    team_id=t.team_id,
                    team_name=t.team_name,
                    manager=t.manager,
                    player_user_id=t.player_user_id,
                    player_name=t.player_name,
                    image_path=t.image_path,
                    image_credit=t.image_credit,
                    image_source_url=t.image_source_url,
                    points=t.points,
                    rank=rank_val,
                    status=t.status,
                    fighters=t.fighters,
                    trait_totals=t.trait_totals,
                    event_history=t.event_history,
                    league_id=t.league_id
                )
            )

        # Final sort order for standings page
        ranked_standings.sort(key=lambda t: (t.rank is None, t.rank or 9999, t.team_name))
        return ranked_standings

    @staticmethod
    def validate_roster(conn: sqlite3.Connection, league_id: int, fighter_ids: List[int]) -> RosterValidation:
        settings = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings").fetchall()}
        
        # Load cost map
        costs = {
            row["id"]: int(row["current_cost"] or 0)
            for row in conn.execute(
                "SELECT id, current_cost FROM fighters WHERE (? IS NULL OR league_id=?)",
                (league_id, league_id),
            )
        }
        
        # Map validation logic
        budget = int(float(settings.get("team_budget", 500)))
        min_size = int(float(settings.get("minimum_team_size", 5)))
        max_size = int(float(settings.get("maximum_team_size", 8)))
        
        member_count = len(fighter_ids)
        duplicates = member_count != len(set(fighter_ids))
        cost = sum(costs.get(fid, 0) for fid in fighter_ids)
        
        reasons = []
        if member_count < min_size:
            reasons.append(f"Needs at least {min_size} fighters")
        if member_count > max_size:
            reasons.append(f"Max {max_size} fighters")
        if duplicates:
            reasons.append("Duplicate fighter")
        if cost > budget:
            reasons.append("Over budget")
            
        status = "VALID" if not reasons else "; ".join(reasons)
        return RosterValidation(
            status=status,
            member_count=member_count,
            cost=cost,
            remaining_budget=budget - cost,
            reasons=reasons
        )
