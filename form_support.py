from datetime import datetime
from flask import request
from exceptions import ValidationError
from season_support import current_season, ensure_active_season


def parse_int_field(name, default=None, minimum=None):
    raw = request.form.get(name, "").strip()
    label = name.replace("_", " ").title()
    if raw == "":
        if default is not None:
            value = default
        else:
            raise ValidationError(f"{label} is required.")
    else:
        try:
            value = int(raw)
        except ValueError as exc:
            raise ValidationError(f"{label} must be a whole number.") from exc
    if minimum is not None and value < minimum:
        raise ValidationError(f"{label} must be at least {minimum}.")
    return value


def parse_optional_float(name):
    value = request.form.get(name, "").strip()
    label = name.replace("_", " ").title()
    if not value:
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise ValidationError(f"{label} must be numeric.") from exc


def attendance_score_form_values(conn):
    score_type = request.form.get("score_type", "").strip().lower()
    if score_type not in {"training", "support"}:
        raise ValidationError("Select a valid attendance score type.")
    attendance_date = request.form.get("attendance_date", "").strip() or datetime.utcnow().date().isoformat()
    try:
        datetime.strptime(attendance_date, "%Y-%m-%d")
    except ValueError as exc:
        raise ValidationError("Attendance date must be in YYYY-MM-DD format.") from exc
    score_units = parse_int_field("score_units", default=1, minimum=1)
    note = request.form.get("note", "").strip()
    season = current_season(conn) or ensure_active_season(conn)
    return {
        "score_type": score_type,
        "attendance_date": attendance_date,
        "score_units": score_units,
        "note": note,
        "season": season,
    }


def fighter_form_values():
    name = request.form.get("name", "").strip()
    if not name:
        raise ValidationError("Name is required.")
    tier = request.form.get("tier", "Tier 3")
    if tier not in {"Tier 1", "Tier 2", "Tier 3"}:
        raise ValidationError("Tier is invalid.")
    return (
        name,
        tier,
        parse_int_field("age", default=0, minimum=0) if request.form.get("age", "").strip() else None,
        parse_optional_float("height"),
        parse_optional_float("weight"),
        parse_int_field("current_cost", default=0, minimum=0),
        request.form.get("notes", "").strip(),
        request.form.get("nickname", "").strip(),
        request.form.get("fighting_style", "").strip(),
        request.form.get("preferred_role", "").strip(),
        request.form.get("role_or_weapon", "").strip(),
        request.form.get("known_for", "").strip(),
        request.form.get("why_buhurt", "").strip(),
        parse_int_field("joined_year", default=0, minimum=0) if request.form.get("joined_year", "").strip() else None,
        request.form.get("reputation", "").strip(),
        request.form.get("image_url", "").strip(),
        request.form.get("image_credit", "").strip(),
        request.form.get("image_source_url", "").strip(),
        request.form.get("bio", "").strip(),
        request.form.get("hero_quote", "").strip(),
    )


def fighter_baseline_values():
    return {
        "training": parse_int_field("training", default=0, minimum=0),
        "support": parse_int_field("support", default=0, minimum=0),
    }


def submitted_fighter_form(existing=None):
    fighter = dict(existing) if existing else {}
    for key in ["name", "tier", "nickname", "fighting_style", "preferred_role", "role_or_weapon", "known_for", "why_buhurt", "reputation", "image_url", "image_credit", "image_source_url", "notes", "bio", "hero_quote"]:
        fighter[key] = request.form.get(key, fighter.get(key, "")).strip()
    fighter["height"] = request.form.get("height", fighter.get("height", ""))
    fighter["weight"] = request.form.get("weight", fighter.get("weight", ""))
    fighter["age"] = request.form.get("age", fighter.get("age", ""))
    fighter["joined_year"] = request.form.get("joined_year", fighter.get("joined_year", ""))
    fighter["current_cost"] = request.form.get("current_cost", fighter.get("current_cost", 0))
    return fighter


def submitted_baseline(existing=None):
    baseline = dict(existing) if existing else {}
    baseline["training"] = request.form.get("training", baseline.get("training", 0))
    baseline["support"] = request.form.get("support", baseline.get("support", 0))
    return baseline
