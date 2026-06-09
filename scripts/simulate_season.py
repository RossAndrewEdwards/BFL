import argparse
import json
import math
import random
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app as app_module


QUALITY_PROFILES = {
    "elite": {
        "share": 0.22,
        "kill_rate": (5, 9),
        "death_rate": (0, 2),
        "sit_down_rate": (0, 1),
        "yellow_chance": 0.08,
        "red_chance": 0.01,
        "medal_weight": 5,
    },
    "steady": {
        "share": 0.50,
        "kill_rate": (2, 6),
        "death_rate": (1, 4),
        "sit_down_rate": (0, 2),
        "yellow_chance": 0.16,
        "red_chance": 0.03,
        "medal_weight": 2,
    },
    "struggling": {
        "share": 0.28,
        "kill_rate": (0, 3),
        "death_rate": (3, 7),
        "sit_down_rate": (1, 4),
        "yellow_chance": 0.28,
        "red_chance": 0.06,
        "medal_weight": 1,
    },
}

DEFAULT_EVENTS = [
    ("2026-05-16", "Leodis Cup", "Kirkstall Abbey, Leeds"),
    ("2026-06-27", "Tournament of Deeds", "Ledbury"),
    ("2026-07-25", "Severnside Clash", "Gloucester"),
    ("2026-10-03", "Heritage Shield", "United Kingdom"),
]


def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def load_rules(conn):
    return {row["key"]: int(row["points"]) for row in conn.execute("SELECT key, points FROM rules")}


def load_fighters(conn):
    return [dict(row) for row in conn.execute("SELECT * FROM fighters ORDER BY id")]


def load_teams(conn):
    teams = [dict(row) for row in conn.execute("SELECT * FROM fantasy_teams ORDER BY team_name")]
    roster_rows = conn.execute(
        """
        SELECT ftf.team_id, ftf.fighter_id
        FROM fantasy_team_fighters ftf
        ORDER BY ftf.team_id, ftf.slot
        """
    ).fetchall()
    rosters = defaultdict(list)
    for row in roster_rows:
        rosters[row["team_id"]].append(row["fighter_id"])
    return teams, rosters


def weighted_quality_order(fighters, rng):
    shuffled = fighters[:]
    rng.shuffle(shuffled)
    tier_bonus = {"Tier 1": 0.18, "Tier 2": 0.0, "Tier 3": -0.14}
    scored = [(rng.random() + tier_bonus.get(fighter["tier"], 0), fighter) for fighter in shuffled]
    scored.sort(reverse=True, key=lambda item: item[0])
    return [fighter for _, fighter in scored]


def assign_quality(fighters, rng):
    ordered = weighted_quality_order(fighters, rng)
    total = len(ordered)
    elite_cut = max(1, round(total * QUALITY_PROFILES["elite"]["share"]))
    steady_cut = elite_cut + round(total * QUALITY_PROFILES["steady"]["share"])
    assignments = {}
    for index, fighter in enumerate(ordered):
        if index < elite_cut:
            quality = "elite"
        elif index < steady_cut:
            quality = "steady"
        else:
            quality = "struggling"
        assignments[fighter["id"]] = quality
    return assignments


def chance(rng, probability):
    return 1 if rng.random() < probability else 0


def event_stats_for_fighter(fighter, quality, rng):
    profile = QUALITY_PROFILES[quality]
    kills = rng.randint(*profile["kill_rate"])
    deaths = rng.randint(*profile["death_rate"])
    if quality == "elite" and rng.random() < 0.25:
        kills += rng.randint(1, 3)
    if quality == "struggling" and rng.random() < 0.25:
        deaths += rng.randint(1, 3)
    return {
        "fighter_id": fighter["id"],
        "fighter_name": fighter["name"],
        "tier": fighter["tier"],
        "quality": quality,
        "competitions": 1,
        "gold_medals": 0,
        "silver_medals": 0,
        "bronze_medals": 0,
        "kills": kills,
        "deaths": deaths,
        "sit_downs": rng.randint(*profile["sit_down_rate"]),
        "yellow_cards": chance(rng, profile["yellow_chance"]),
        "red_cards": chance(rng, profile["red_chance"]),
    }


def award_medals(event_rows, rng):
    if len(event_rows) < 3:
        return
    weighted = []
    for row in event_rows:
        weight = QUALITY_PROFILES[row["quality"]]["medal_weight"] + max(0, row["kills"] - row["deaths"])
        weighted.append((max(1, weight), row))
    winners = []
    pool = weighted[:]
    for _ in range(3):
        total_weight = sum(weight for weight, _ in pool)
        pick = rng.uniform(0, total_weight)
        running = 0
        for index, (weight, row) in enumerate(pool):
            running += weight
            if running >= pick:
                winners.append(row)
                pool.pop(index)
                break
    winners[0]["gold_medals"] = 1
    winners[1]["silver_medals"] = 1
    winners[2]["bronze_medals"] = 1


def simulate_events(fighters, quality_by_fighter, events, participation_rate, rng):
    event_results = []
    event_size = max(1, math.ceil(len(fighters) * participation_rate))
    for event_date, event_name, location in events:
        participants = rng.sample(fighters, event_size)
        rows = [event_stats_for_fighter(fighter, quality_by_fighter[fighter["id"]], rng) for fighter in participants]
        award_medals(rows, rng)
        for row in rows:
            row["event_date"] = event_date
            row["event_name"] = event_name
            row["location"] = location
        event_results.extend(rows)
    return event_results


def simulate_weekly_activity(fighters, weeks, rng):
    activity = {}
    for fighter in fighters:
        training = 0
        support = 0
        weekly = []
        for week in range(1, weeks + 1):
            week_training = rng.randint(0, 3)
            week_support = 1 if rng.random() < 0.18 else 0
            training += week_training
            support += week_support
            weekly.append({"week": week, "training": week_training, "support": week_support})
        activity[fighter["id"]] = {"training": training, "support": support, "weekly": weekly}
    return activity


def score_row(row, rules):
    return sum(int(row.get(key, 0) or 0) * rules.get(key, 0) for key in app_module.STAT_KEYS)


def aggregate_fighters(fighters, event_results, weekly_activity, rules):
    totals = {}
    for fighter in fighters:
        activity = weekly_activity[fighter["id"]]
        totals[fighter["id"]] = {
            "id": fighter["id"],
            "name": fighter["name"],
            "tier": fighter["tier"],
            "current_cost": int(fighter["current_cost"] or 0),
            "training": activity["training"],
            "support": activity["support"],
            "competitions": 0,
            "gold_medals": 0,
            "silver_medals": 0,
            "bronze_medals": 0,
            "kills": 0,
            "deaths": 0,
            "sit_downs": 0,
            "yellow_cards": 0,
            "red_cards": 0,
        }
    for result in event_results:
        row = totals[result["fighter_id"]]
        for key in app_module.EVENT_STAT_KEYS:
            row[key] += int(result[key])
        row["competitions"] += 1
    for row in totals.values():
        row["total_points"] = score_row(row, rules)
        row["event_points"] = sum(int(row.get(key, 0) or 0) * rules.get(key, 0) for key in ["competitions", *app_module.EVENT_STAT_KEYS])
        row["activity_points"] = row["training"] * rules.get("training", 0) + row["support"] * rules.get("support", 0)
        row["points_per_cost"] = row["total_points"] / max(1, row["current_cost"])
    ranked = sorted(totals.values(), key=lambda row: (-row["total_points"], row["name"]))
    for rank, row in enumerate(ranked, start=1):
        row["rank"] = rank
    return ranked


def score_teams(teams, rosters, fighter_totals):
    by_id = {row["id"]: row for row in fighter_totals}
    rows = []
    for team in teams:
        fighter_ids = rosters.get(team["id"], [])
        fighters = [by_id[fighter_id] for fighter_id in fighter_ids if fighter_id in by_id]
        rows.append(
            {
                "team_name": team["team_name"],
                "manager": team["manager"],
                "player_user_id": team.get("player_user_id"),
                "points": sum(fighter["total_points"] for fighter in fighters),
                "cost": sum(fighter["current_cost"] for fighter in fighters),
                "roster_count": len(fighters),
                "fighters": fighters,
            }
        )
    rows.sort(key=lambda row: (-row["points"], row["team_name"]))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


def gaming_signals(fighter_totals, team_totals, quality_by_fighter, rules):
    signals = []
    if not fighter_totals:
        return signals
    top_ten = fighter_totals[:10]
    cheap_top = [row for row in top_ten if row["current_cost"] <= 50]
    if cheap_top:
        signals.append(
            f"{len(cheap_top)} of the top 10 fighters cost 50 or less. Cheap high performers may be underpriced."
        )
    top_activity_share = max(
        row["activity_points"] / max(1, row["activity_points"] + max(0, row["event_points"]))
        for row in top_ten
        if row["total_points"] > 0
    )
    if top_activity_share > 0.45:
        signals.append(
            f"One fighter gets {top_activity_share:.0%} of their points from weekly training/support, so non-event activity may be too influential."
        )
    attendance_leaders = [row for row in top_ten if row["competitions"] == max(item["competitions"] for item in fighter_totals)]
    if len(attendance_leaders) >= 5:
        signals.append("Most top fighters are also maximum-attendance fighters. Availability may dominate quality.")
    struggling_top = [row for row in top_ten if quality_by_fighter[row["id"]] == "struggling"]
    if struggling_top:
        signals.append(
            f"{len(struggling_top)} simulated struggling fighters reached the top 10, mostly through attendance/activity variance."
        )
    if team_totals:
        leader = team_totals[0]
        if len(team_totals) > 1 and leader["points"] - team_totals[1]["points"] > 120:
            signals.append(
                f"The leading team is ahead by {leader['points'] - team_totals[1]['points']} points, which may indicate stacking elite fighters is too decisive."
            )
        low_cost_leader = leader["cost"] < 350 and leader["points"] > 0
        if low_cost_leader:
            signals.append("The winning team is well under budget, which suggests cost may not constrain roster strength enough.")
    if rules.get("support", 0) >= rules.get("kills", 0):
        signals.append("Support is worth at least as much as a kill. That may be fine, but it is an obvious lever for gaming if support is easy to earn.")
    return signals or ["No obvious exploit jumped out in this run. Rerun with different seeds before trusting that too much."]


def markdown_table(rows, headers, row_builder, limit=None):
    selected = rows[:limit] if limit else rows
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in selected:
        lines.append("| " + " | ".join(str(value) for value in row_builder(row)) + " |")
    return "\n".join(lines)


def build_report(args, fighters, events, quality_by_fighter, event_results, weekly_activity, fighter_totals, team_totals, rules, signals):
    quality_counts = Counter(quality_by_fighter.values())
    attendance = Counter(row["fighter_id"] for row in event_results)
    event_lines = [f"- {event_date}: {event_name}, {location}" for event_date, event_name, location in events]
    top_fighters = markdown_table(
        fighter_totals,
        ["Rank", "Fighter", "Band", "Tier", "Pts", "Events", "Train", "Support", "Kills", "Deaths", "Cost", "Pts/Cost"],
        lambda row: [
            row["rank"],
            row["name"],
            quality_by_fighter[row["id"]],
            row["tier"],
            row["total_points"],
            row["competitions"],
            row["training"],
            row["support"],
            row["kills"],
            row["deaths"],
            row["current_cost"],
            f"{row['points_per_cost']:.2f}",
        ],
        limit=12,
    )
    top_value = markdown_table(
        sorted(fighter_totals, key=lambda row: (-row["points_per_cost"], -row["total_points"], row["name"])),
        ["Fighter", "Band", "Tier", "Pts", "Cost", "Pts/Cost"],
        lambda row: [row["name"], quality_by_fighter[row["id"]], row["tier"], row["total_points"], row["current_cost"], f"{row['points_per_cost']:.2f}"],
        limit=10,
    )
    team_table = markdown_table(
        team_totals,
        ["Rank", "Team", "Manager", "Pts", "Cost", "Roster"],
        lambda row: [row["rank"], row["team_name"], row["manager"], row["points"], row["cost"], row["roster_count"]],
        limit=10,
    )
    attendance_table = markdown_table(
        sorted(fighter_totals, key=lambda row: (-attendance[row["id"]], row["name"])),
        ["Fighter", "Events"],
        lambda row: [row["name"], attendance[row["id"]]],
        limit=10,
    )
    signal_lines = "\n".join(f"- {signal}" for signal in signals)
    return f"""# Mock Season Simulation

Seed: `{args.seed}`
Events simulated: `{len(events)}`
Weekly activity weeks: `{args.weeks}`
Per-event participation: `{args.participation_rate:.0%}` of fighters
Fighters: `{len(fighters)}`

## Event Calendar
{chr(10).join(event_lines)}

## Quality Bands
- Elite: {quality_counts["elite"]} fighters
- Steady: {quality_counts["steady"]} fighters
- Struggling: {quality_counts["struggling"]} fighters

## Top Fighters
{top_fighters}

## Best Value Fighters
{top_value}

## Team Results
{team_table if team_totals else "No fantasy teams exist in the current database, so team-level results were skipped."}

## Attendance Sample
{attendance_table}

## Balance / Gaming Signals
{signal_lines}

## Notes
- This simulation does not write to the app database.
- Each event randomly selects a new {args.participation_rate:.0%} fighter field.
- Fighter quality is stable across the season, but event results still include variance.
- Training and support are fully randomised week by week for every fighter.
"""


def parse_args():
    parser = argparse.ArgumentParser(description="Generate a non-destructive mock fantasy season.")
    parser.add_argument("--db", default=str(app_module.DB_PATH), help="SQLite database path.")
    parser.add_argument("--seed", type=int, default=20260429, help="Random seed for repeatable seasons.")
    parser.add_argument("--weeks", type=int, default=26, help="Number of weekly training/support rolls.")
    parser.add_argument("--participation-rate", type=float, default=0.8, help="Share of fighters selected for each event.")
    parser.add_argument("--output", default=str(ROOT / ".tmp" / "mock_season_report.md"), help="Markdown report path.")
    parser.add_argument("--json-output", default=str(ROOT / ".tmp" / "mock_season_report.json"), help="JSON data path.")
    return parser.parse_args()


def main():
    args = parse_args()
    if not 0 < args.participation_rate <= 1:
        raise SystemExit("--participation-rate must be greater than 0 and no more than 1.")
    app_module.init_db()
    rng = random.Random(args.seed)
    conn = connect(args.db)
    fighters = load_fighters(conn)
    if not fighters:
        raise SystemExit("No fighters found. Seed the app database before simulating a season.")
    rules = load_rules(conn)
    teams, rosters = load_teams(conn)
    events = DEFAULT_EVENTS
    quality_by_fighter = assign_quality(fighters, rng)
    event_results = simulate_events(fighters, quality_by_fighter, events, args.participation_rate, rng)
    weekly_activity = simulate_weekly_activity(fighters, args.weeks, rng)
    fighter_totals = aggregate_fighters(fighters, event_results, weekly_activity, rules)
    team_totals = score_teams(teams, rosters, fighter_totals)
    signals = gaming_signals(fighter_totals, team_totals, quality_by_fighter, rules)
    report = build_report(args, fighters, events, quality_by_fighter, event_results, weekly_activity, fighter_totals, team_totals, rules, signals)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    json_path = Path(args.json_output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(
            {
                "seed": args.seed,
                "events": events,
                "quality_by_fighter": quality_by_fighter,
                "event_results": event_results,
                "weekly_activity": weekly_activity,
                "fighter_totals": fighter_totals,
                "team_totals": team_totals,
                "signals": signals,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Mock season report written to {output_path}")
    print(f"Simulation data written to {json_path}")
    print("")
    print("\n".join(report.splitlines()[:42]))


if __name__ == "__main__":
    main()
