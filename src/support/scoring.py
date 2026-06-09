def float_setting(settings, key, default=0.0):
    try:
        return float(settings.get(key, default))
    except Exception:
        return float(default)


def int_setting(settings, key, default=0):
    try:
        return int(float(settings.get(key, default)))
    except Exception:
        return default


def round_to_unit(value, unit):
    return int(round(value / unit) * unit)


def season_cost_settings_from_settings(settings, int_setting_fn=None):
    # Support optional int_setting_fn for backwards compatibility, fallback to local int_setting
    fn = int_setting_fn or int_setting
    return {
        "target_pick_rate": float_setting(settings, "season_pick_rate_target", 0.2),
        "sensitivity": float_setting(settings, "season_cost_sensitivity", 1.0),
        "adjustment_cap": max(0.0, float_setting(settings, "season_cost_adjustment_cap", 0.2)),
        "round_unit": max(1, fn(settings, "season_cost_round_unit", 5)),
        "min_cost": max(0, fn(settings, "season_min_cost", 25)),
        "max_cost": max(0, fn(settings, "season_max_cost", 250)),
    }


def calculate_season_cost_changes(fighters, teams, formula):
    team_count = len(teams)
    fighter_pick_counts = {fighter["id"]: 0 for fighter in fighters}
    for team in teams:
        for fighter in team["fighters"]:
            fighter_pick_counts[fighter["id"]] = fighter_pick_counts.get(fighter["id"], 0) + 1

    changes = []
    cap = formula["adjustment_cap"]
    target = formula["target_pick_rate"]
    sensitivity = formula["sensitivity"]
    round_unit = formula["round_unit"]
    min_cost = formula["min_cost"]
    max_cost = max(formula["max_cost"], min_cost)
    for fighter in fighters:
        pick_count = fighter_pick_counts.get(fighter["id"], 0)
        pick_rate = (pick_count / team_count) if team_count else 0.0
        raw_adjustment = (pick_rate - target) * sensitivity
        applied_adjustment = max(-cap, min(cap, raw_adjustment))
        candidate_cost = fighter["current_cost"] * (1 + applied_adjustment)
        rounded_cost = round_to_unit(candidate_cost, round_unit)
        new_cost = min(max_cost, max(min_cost, rounded_cost))
        changes.append(
            {
                "fighter_id": fighter["id"],
                "fighter_name": fighter["name"],
                "old_cost": fighter["current_cost"],
                "new_cost": new_cost,
                "pick_count": pick_count,
                "team_count": team_count,
                "pick_rate": pick_rate,
                "target_pick_rate": target,
                "sensitivity": sensitivity,
                "raw_adjustment": raw_adjustment,
                "applied_adjustment": applied_adjustment,
                "clamp_limit": cap,
                "round_unit": round_unit,
                "min_cost": min_cost,
                "max_cost": max_cost,
            }
        )
    return changes


def validate_team(team, fighters, costs, settings, points_by_fighter=None):
    budget = int_setting(settings, "team_budget", 500)
    min_size = int_setting(settings, "minimum_team_size", 5)
    max_size = int_setting(settings, "maximum_team_size", 8)
    ids = [f["id"] for f in fighters]
    member_count = len(ids)
    duplicates = member_count != len(set(ids))
    cost = sum(costs.get(fid, 0) for fid in ids)
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
    points = sum(points_by_fighter.get(fid, 0) for fid in ids) if points_by_fighter else 0
    return {
        "member_count": member_count,
        "cost": cost,
        "remaining": budget - cost,
        "status": status,
        "points": points,
    }


def event_points(row, rules, event_stat_keys):
    return sum(int(row[k] or 0) * rules.get(k, 0) for k in event_stat_keys)


def normalize_public_metric(rows, raw_key, output_key, include_zero_baseline=False):
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


def apply_public_profile_ratings(rows, public_profile_stat_order, formula_settings):
    rows = [row for row in rows if row]
    if not rows:
        return rows
    for row in rows:
        row["glory_raw"] = (
            row.get("competitions", 0) * formula_settings["glory_competitions_weight"]
            + row.get("special_awards", 0) * formula_settings["glory_special_awards_weight"]
            + row.get("gold_medals", 0) * formula_settings["glory_gold_weight"]
            + row.get("silver_medals", 0) * formula_settings["glory_silver_weight"]
            + row.get("bronze_medals", 0) * formula_settings["glory_bronze_weight"]
        )
        row["discipline_raw"] = (
            row.get("training", 0) * formula_settings["discipline_training_weight"]
            + row.get("competitions", 0) * formula_settings["discipline_competitions_weight"]
            - row.get("yellow_cards", 0) * formula_settings["discipline_yellow_penalty"]
            - row.get("red_cards", 0) * formula_settings["discipline_red_penalty"]
        )
        row["lethality_raw"] = float(row.get("kd_ratio") or 0) * formula_settings["lethality_kd_weight"]
        row["resilience_raw"] = (
            row.get("rounds_fought", 0) * formula_settings["resilience_rounds_weight"]
            - row.get("deaths", 0) * formula_settings["resilience_deaths_penalty"]
            - row.get("sit_downs", 0) * formula_settings["resilience_sit_downs_penalty"]
        )
        row["crowd_favourite_raw"] = (
            row.get("kills", 0) * formula_settings["crowd_kills_weight"]
            + row.get("gold_medals", 0) * formula_settings["crowd_gold_weight"]
            + row.get("silver_medals", 0) * formula_settings["crowd_silver_weight"]
            + row.get("bronze_medals", 0) * formula_settings["crowd_bronze_weight"]
            + row.get("special_awards", 0) * formula_settings["crowd_special_awards_weight"]
            + (float(row.get("ownership_percent") or 0) * 100 * formula_settings["crowd_ownership_weight"])
        )
        row["synergy_raw"] = (
            row.get("support", 0) * formula_settings["synergy_support_weight"]
            + row.get("assists", 0) * formula_settings["synergy_assists_weight"]
            + row.get("competitions", 0) * formula_settings["synergy_competitions_weight"]
            - row.get("yellow_cards", 0) * formula_settings["synergy_yellow_penalty"]
            - row.get("red_cards", 0) * formula_settings["synergy_red_penalty"]
        )
    normalize_public_metric(rows, "glory_raw", "glory", include_zero_baseline=True)
    normalize_public_metric(rows, "discipline_raw", "discipline_rating", include_zero_baseline=True)
    normalize_public_metric(rows, "lethality_raw", "lethality", include_zero_baseline=True)
    normalize_public_metric(rows, "resilience_raw", "resilience", include_zero_baseline=True)
    normalize_public_metric(rows, "crowd_favourite_raw", "crowd_favourite", include_zero_baseline=True)
    normalize_public_metric(rows, "synergy_raw", "synergy", include_zero_baseline=True)
    for row in rows:
        row["overall_raw"] = sum(float(row.get(key) or 0) for key, _ in public_profile_stat_order) / len(public_profile_stat_order)
    normalize_public_metric(rows, "overall_raw", "overall_rating", include_zero_baseline=True)
    for row in rows:
        for key, _label in public_profile_stat_order:
            row[key] = int(round(float(row.get(key) or 0)))
        row["overall_rating"] = float(row.get("overall_rating") or 0)
    return rows
