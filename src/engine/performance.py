import datetime
from typing import List, Dict, Any, Optional, Tuple

from src.exceptions import ValidationError

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

TIER_THEME_MAP = {
    "tier-1": {"class_name": "tier-1", "label": "Tier 1", "legend": "Gold"},
    "tier-2": {"class_name": "tier-2", "label": "Tier 2", "legend": "Silver"},
    "tier-3": {"class_name": "tier-3", "label": "Tier 3", "legend": "Bronze"},
    "tier-4": {"class_name": "tier-4", "label": "Tier 4+", "legend": "Secondary"},
    "tier-unknown": {"class_name": "tier-unknown", "label": "Unknown Tier", "legend": "Neutral"},
}

EVENT_STAT_KEYS = [
    "special_awards", "gold_medals", "silver_medals", "bronze_medals", "kills", "assists", "deaths", "sit_downs", "yellow_cards", "red_cards"
]


class FighterPerformanceEngine:
    """
    Consolidated domain engine for computing fighter performance ratings,
    0-100 normalization scales, latest event result summaries, and rank movements.
    """
    def __init__(self, conn):
        self._conn = conn

    def normalize_metric(self, rows: List[Dict[str, Any]], raw_key: str, output_key: str, include_zero_baseline: bool = False) -> None:
        values = [float(row.get(raw_key) or 0) for row in rows]
        if include_zero_baseline:
            values.append(0.0)
        if not values:
            return
        low = min(values)
        high = max(values)
        if high == low:
            for row in rows:
                row[output_key] = 0.0
            return
        for row in rows:
            row[output_key] = ((float(row.get(raw_key) or 0) - low) / (high - low)) * 100

    def calculate_ratings(self, rows: List[Dict[str, Any]], formula_settings: Dict[str, float]) -> List[Dict[str, Any]]:
        rows = [row for row in rows if row]
        if not rows:
            return rows
            
        for row in rows:
            row["glory_raw"] = (
                row.get("competitions", 0) * formula_settings.get("glory_competitions_weight", 3.0)
                + row.get("special_awards", 0) * formula_settings.get("glory_special_awards_weight", 10.0)
                + row.get("gold_medals", 0) * formula_settings.get("glory_gold_weight", 8.0)
                + row.get("silver_medals", 0) * formula_settings.get("glory_silver_weight", 6.0)
                + row.get("bronze_medals", 0) * formula_settings.get("glory_bronze_weight", 5.0)
            )
            row["discipline_raw"] = (
                row.get("training", 0) * formula_settings.get("discipline_training_weight", 1.0)
                + row.get("competitions", 0) * formula_settings.get("discipline_competitions_weight", 3.0)
                - row.get("yellow_cards", 0) * formula_settings.get("discipline_yellow_penalty", 5.0)
                - row.get("red_cards", 0) * formula_settings.get("discipline_red_penalty", 10.0)
            )
            row["lethality_raw"] = float(row.get("kd_ratio") or 0) * formula_settings.get("lethality_kd_weight", 1.0)
            row["resilience_raw"] = (
                row.get("rounds_fought", 0) * formula_settings.get("resilience_rounds_weight", 1.0)
                - row.get("deaths", 0) * formula_settings.get("resilience_deaths_penalty", 1.0)
                - row.get("sit_downs", 0) * formula_settings.get("resilience_sit_downs_penalty", 1.0)
            )
            row["crowd_favourite_raw"] = (
                row.get("kills", 0) * formula_settings.get("crowd_kills_weight", 1.0)
                + row.get("gold_medals", 0) * formula_settings.get("crowd_gold_weight", 1.0)
                + row.get("silver_medals", 0) * formula_settings.get("crowd_silver_weight", 1.0)
                + row.get("bronze_medals", 0) * formula_settings.get("crowd_bronze_weight", 1.0)
                + row.get("special_awards", 0) * formula_settings.get("crowd_special_awards_weight", 1.0)
                + (float(row.get("ownership_percent") or 0) * 100 * formula_settings.get("crowd_ownership_weight", 5.0))
            )
            row["synergy_raw"] = (
                row.get("support", 0) * formula_settings.get("synergy_support_weight", 3.0)
                + row.get("assists", 0) * formula_settings.get("synergy_assists_weight", 3.0)
                + row.get("competitions", 0) * formula_settings.get("synergy_competitions_weight", 3.0)
                - row.get("yellow_cards", 0) * formula_settings.get("synergy_yellow_penalty", 5.0)
                - row.get("red_cards", 0) * formula_settings.get("synergy_red_penalty", 10.0)
            )
            
        self.normalize_metric(rows, "glory_raw", "glory", include_zero_baseline=True)
        self.normalize_metric(rows, "discipline_raw", "discipline_rating", include_zero_baseline=True)
        self.normalize_metric(rows, "lethality_raw", "lethality", include_zero_baseline=True)
        self.normalize_metric(rows, "resilience_raw", "resilience", include_zero_baseline=True)
        self.normalize_metric(rows, "crowd_favourite_raw", "crowd_favourite", include_zero_baseline=True)
        self.normalize_metric(rows, "synergy_raw", "synergy", include_zero_baseline=True)
        
        for row in rows:
            row["overall_raw"] = sum(float(row.get(key) or 0) for key, _ in PUBLIC_PROFILE_STAT_ORDER) / len(PUBLIC_PROFILE_STAT_ORDER)
            
        self.normalize_metric(rows, "overall_raw", "overall_rating", include_zero_baseline=True)
        
        for row in rows:
            for key, _label in PUBLIC_PROFILE_STAT_ORDER:
                row[key] = int(round(float(row.get(key) or 0)))
            row["overall_rating"] = float(row.get("overall_rating") or 0)
            
        return rows

    def get_latest_event_payload(self, league_id_override: Optional[int] = None) -> Optional[Dict[str, Any]]:
        from src.support.auth import scoped_league_id, effective_league_id
        from src.engine.roster import RosterRankingsEngine
        from src.support.ui import FighterPresenter, tier_theme, event_summary_text
        from src.support.scoring import event_points
        
        league_id = league_id_override if league_id_override is not None else scoped_league_id(self._conn)
        event = self._conn.execute(
            """
            SELECT er.scheduled_event_id,
                   er.event_date,
                   er.event_name,
                   COUNT(*) AS result_count,
                   eb.headline,
                   eb.subheading
            FROM event_results er
            LEFT JOIN event_banners eb ON eb.id = er.scheduled_event_id
            WHERE (? IS NULL OR er.league_id=?)
            GROUP BY er.scheduled_event_id, er.event_date, er.event_name
            ORDER BY er.event_date DESC, MAX(er.id) DESC
            LIMIT 1
            """,
            (league_id, league_id),
        ).fetchone()
        if not event:
            return None

        event = dict(event)
        
        rules = {r["key"]: r["points"] for r in self._conn.execute("SELECT key, points FROM rules")}
        
        # Load performance ratings via rankings engine
        leaderboard = RosterRankingsEngine.get_fighter_leaderboard(self._conn, league_id)
        leaderboard_lookup = {}
        for f in leaderboard:
            fields = dict(f.profile_fields)
            fields["rank"] = f.rank
            leaderboard_lookup[f.fighter_id] = fields
        
        fighter_rows = []
        fighter_results = self._conn.execute(
            """
            SELECT er.*,
                   f.name,
                   f.tier,
                   f.nickname,
                   f.preferred_role,
                   f.fighting_style,
                   f.image_url,
                   f.image_credit,
                   f.image_source_url
            FROM event_results er
            JOIN fighters f ON f.id = er.fighter_id
            WHERE ((er.scheduled_event_id = ?) OR (? IS NULL AND er.scheduled_event_id IS NULL AND er.event_date = ? AND er.event_name = ?))
              AND (? IS NULL OR er.league_id=?)
            ORDER BY f.name
            """,
            (event.get("scheduled_event_id"), event.get("scheduled_event_id"), event["event_date"], event["event_name"], league_id, league_id),
        ).fetchall()
        
        for row in fighter_results:
            fighter = dict(row)
            fighter.update(
                {
                    key: leaderboard_lookup.get(fighter["fighter_id"], {}).get(key, 0)
                    for key, _label in PUBLIC_PROFILE_STAT_ORDER
                }
            )
            fighter["overall_rating"] = leaderboard_lookup.get(fighter["fighter_id"], {}).get("overall_rating", 0)
            fighter["event_points"] = event_points(fighter, rules, EVENT_STAT_KEYS)
            fighter["tier_theme"] = tier_theme(fighter.get("tier"), TIER_THEME_MAP)
            fighter_rows.append(fighter)
            
        fighter_rows.sort(key=lambda row: (-row["event_points"], row["name"]))
        for index, row in enumerate(fighter_rows, start=1):
            row["event_rank"] = index
            presenter = FighterPresenter(row, PUBLIC_PROFILE_STAT_ORDER)
            row["public_display"] = {
                "spotlight_label": presenter.spotlight_label(context="leaderboard"),
                "summary": presenter.summary,
                "stats": presenter.stats,
            }

        fighter_event_points = {row["fighter_id"]: int(row["event_points"] or 0) for row in fighter_rows}
        previous_fighter_rows = []
        for f_id, f_fields in leaderboard_lookup.items():
            previous_total = int(f_fields.get("total_points") or 0) - fighter_event_points.get(f_id, 0)
            previous_fighter_rows.append((f_id, previous_total, f_fields.get("name", "")))
            
        previous_fighter_rows.sort(key=lambda row: (-row[1], row[2].lower(), row[0]))
        previous_fighter_ranks = {fighter_id: index for index, (fighter_id, _points, _name) in enumerate(previous_fighter_rows, start=1)}
        for row in fighter_rows:
            current_rank = leaderboard_lookup.get(row["fighter_id"], {}).get("rank")
            row["movement"] = self._movement(previous_fighter_ranks.get(row["fighter_id"]), current_rank)

        team_entries = []
        from src.app import team_rows
        all_teams = team_rows(self._conn)
        fighter_points = {row["fighter_id"]: row["event_points"] for row in fighter_rows}
        for team in all_teams:
            event_total = sum(fighter_points.get(fighter["id"], 0) for fighter in team["fighters"])
            if event_total <= 0:
                continue
            team_entry = dict(team)
            team_entry["event_points"] = event_total
            team_entry["event_fighter_count"] = sum(1 for fighter in team["fighters"] if fighter_points.get(fighter["id"], 0) > 0)
            team_entries.append(team_entry)
            
        team_entries.sort(key=lambda row: (-row["event_points"], row["team_name"]))
        for index, row in enumerate(team_entries, start=1):
            row["event_rank"] = index

        previous_team_rows = []
        for team in all_teams:
            previous_total = int(team.get("points") or 0) - int(sum(fighter_points.get(fighter["id"], 0) for fighter in team["fighters"]) or 0)
            previous_team_rows.append((team["id"], previous_total, team.get("team_name", "")))
            
        previous_team_rows.sort(key=lambda row: (-row[1], row[2].lower(), row[0]))
        previous_team_ranks = {team_id: index for index, (team_id, _points, _name) in enumerate(previous_team_rows, start=1)}
        for row in team_entries:
            row["movement"] = self._movement(previous_team_ranks.get(row["id"]), row.get("rank"))

        top_fighters = fighter_rows[:3]
        top_teams = team_entries[:3]
        best_team = top_teams[0] if top_teams else None
        fighter_movers = sorted(
            [row for row in fighter_rows if row.get("movement") and row["movement"]["direction"] == "up"],
            key=lambda row: (-row["movement"]["delta"], -row["event_points"], row["name"]),
        )
        team_movers = sorted(
            [row for row in team_entries if row.get("movement") and row["movement"]["direction"] == "up"],
            key=lambda row: (-row["movement"]["delta"], -row["event_points"], row["team_name"]),
        )
        
        event["summary"] = event_summary_text(event, top_fighters, best_team)
        event["query_args"] = (
            {"scheduled_event_id": event["scheduled_event_id"]}
            if event.get("scheduled_event_id")
            else {"event_date": event["event_date"], "event_name": event["event_name"]}
        )
        return {
            "event": event,
            "top_fighters": top_fighters,
            "top_teams": top_teams,
            "best_team": best_team,
            "fighter_rows": fighter_rows,
            "team_rows": team_entries,
            "fighter_movers": fighter_movers,
            "team_movers": team_movers,
        }

    def _movement(self, previous_rank, current_rank):
        if not current_rank:
            return None
        if previous_rank is None:
            return {
                "previous_rank": None,
                "current_rank": current_rank,
                "direction": "new",
                "delta": 0,
                "label": "New",
            }
        if previous_rank > current_rank:
            delta = previous_rank - current_rank
            return {
                "previous_rank": previous_rank,
                "current_rank": current_rank,
                "direction": "up",
                "delta": delta,
                "label": f"Up {delta}",
            }
        if previous_rank < current_rank:
            delta = current_rank - previous_rank
            return {
                "previous_rank": previous_rank,
                "current_rank": current_rank,
                "direction": "down",
                "delta": delta,
                "label": f"Down {delta}",
            }
        return {
            "previous_rank": previous_rank,
            "current_rank": current_rank,
            "direction": "stay",
            "delta": 0,
            "label": "Held",
        }
