import re


def query_text(value):
    return " ".join(str(value or "").strip().lower().split())


def tier_theme(tier_value, tier_theme_map):
    text = " ".join(str(tier_value or "").split())
    match = re.search(r"(\d+)", text)
    if match:
        tier_number = int(match.group(1))
        if tier_number == 1:
            return dict(tier_theme_map["tier-1"])
        if tier_number == 2:
            return dict(tier_theme_map["tier-2"])
        if tier_number == 3:
            return dict(tier_theme_map["tier-3"])
        if tier_number >= 4:
            return dict(tier_theme_map["tier-4"])
    return dict(tier_theme_map["tier-unknown"])


def tier_legend_items(tier_theme_map, tier_theme_order):
    return [dict(tier_theme_map[key]) for key in tier_theme_order]


class FighterPresenter:
    """
    Unified UI presenter for fighter display details, spotlight labels,
    form indicators, summary descriptions, and stats formatting.
    """
    def __init__(self, fighter, stat_order=None):
        self.fighter = dict(fighter or {})
        self.stat_order = stat_order or []

    def spotlight_label(self, context="leaderboard") -> str:
        rank = int(self.fighter.get("rank") or 0)
        if context == "home":
            if rank == 1:
                return "Featured Fighter"
            if rank <= 5:
                return "Top Performer"
            return "Rising Fighter"
        if rank == 1:
            return "Top Performer"
        if rank <= 10:
            return "Rising Fighter"
        return "Featured Fighter"

    @property
    def form_label(self) -> str:
        rank = int(self.fighter.get("rank") or 0)
        if rank <= 0:
            return "Unranked"
        if rank <= 3:
            return "Elite"
        if rank <= 8:
            return "Hot streak"
        if rank <= 16:
            return "Climbing"
        return "Steady"

    @property
    def affiliation(self) -> str:
        return self.fighter.get("club_name") or self.fighter.get("team_name") or self.fighter.get("club") or ""

    @property
    def summary(self) -> str:
        return self.fighter.get("nickname") or self.fighter.get("preferred_role") or self.fighter.get("fighting_style") or "Profile details to be updated."

    @property
    def stats(self) -> list:
        return [{"label": label, "value": self.fighter.get(key, 0)} for key, label in self.stat_order]

    def to_display_dict(self, context="leaderboard") -> dict:
        return {
            "spotlight_label": self.spotlight_label(context=context),
            "form_label": self.form_label,
            "summary": self.summary,
            "stats": self.stats,
        }


def public_fighter_form_label(rank):
    return FighterPresenter({"rank": rank}).form_label


def public_fighter_spotlight_label(fighter, context="leaderboard"):
    return FighterPresenter(fighter).spotlight_label(context=context)


def public_fighter_display(fighter, public_profile_stat_order, public_fighter_spotlight_label_fn=None, public_fighter_form_label_fn=None, context="leaderboard"):
    return FighterPresenter(fighter, public_profile_stat_order).to_display_dict(context=context)


def public_top_fighter_label(rank, public_fighter_spotlight_label_fn=None):
    rank = int(rank or 0)
    if rank == 1:
        return "Current Leader"
    if rank == 2:
        return "Top Performer"
    if rank == 3:
        return "In Form"
    return FighterPresenter({"rank": rank}).spotlight_label(context="leaderboard")


def public_fighter_affiliation(fighter):
    return FighterPresenter(fighter).affiliation


def event_summary_text(event, top_fighters, best_team):
    if event.get("subheading"):
        return event["subheading"]
    if event.get("headline"):
        return event["headline"]
    if top_fighters and best_team:
        return f"{top_fighters[0]['name']} led the latest card while {best_team['team_name']} posted the strongest fantasy surge."
    if top_fighters:
        return f"{top_fighters[0]['name']} set the pace in the latest scored event."
    if best_team:
        return f"{best_team['team_name']} delivered the strongest fantasy swing from the latest event."
    return "Results will fill in here as soon as the latest event has been scored."


def row_value(row, accessor):
    if callable(accessor):
        return accessor(row)
    if isinstance(row, dict):
        return row.get(accessor)
    try:
        return row[accessor]
    except (KeyError, IndexError, TypeError):
        return getattr(row, accessor, None)


def flatten_search_values(value):
    if value is None:
        return []
    if isinstance(value, dict):
        values = value.values()
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        return [str(value)]
    output = []
    for item in values:
        output.extend(flatten_search_values(item))
    return output


def matches_search_query(row, search_value, fields, query_text_fn):
    needle = query_text_fn(search_value)
    if not needle:
        return True
    haystacks = []
    for field in fields:
        haystacks.extend(flatten_search_values(row_value(row, field)))
    return needle in query_text_fn(" ".join(haystacks))


def filter_option_rows(rows, accessor, query_text_fn, sort=True):
    seen = set()
    options = []
    for row in rows:
        value = row_value(row, accessor)
        if value in (None, ""):
            continue
        option_value = str(value)
        key = query_text_fn(option_value)
        if key in seen:
            continue
        seen.add(key)
        options.append({"value": option_value, "label": option_value})
    if sort:
        options.sort(key=lambda option: query_text_fn(option["label"]))
    return options


def normalize_toolbar_options(options):
    normalized = []
    for option in options:
        if isinstance(option, dict):
            value = option.get("value", "")
            label = option.get("label", value)
        elif isinstance(option, (list, tuple)) and len(option) == 2:
            value, label = option
        else:
            value = option
            label = option
        normalized.append({"value": str(value), "label": str(label)})
    return normalized


def normalize_sort_value(value, query_text_fn):
    if isinstance(value, str):
        return (value is None, query_text_fn(value))
    return (value is None, value)


def build_reset_url(path, persist_params, urlencode_fn):
    if not persist_params:
        return path
    return f"{path}?{urlencode_fn(persist_params, doseq=True)}"


class CollectionFilterCoordinator:
    """
    Deep coordinator class to encapsulate collection filtering, query search matching,
    and sorting logic.
    """
    def __init__(self, rows, query_text_fn, urlencode_fn):
        self.rows = list(rows)
        self.query_text_fn = query_text_fn
        self.urlencode_fn = urlencode_fn

    def apply(
        self,
        query_args,
        request_path,
        search_fields,
        filters=None,
        sort_options=None,
        default_sort="default",
        search_placeholder="Search",
        param_prefix="",
    ):
        rows = self.rows
        filters = filters or []
        sort_options = sort_options or []
        search_param = f"{param_prefix}q"
        sort_param = f"{param_prefix}sort"
        used_params = {search_param, sort_param}
        search_value = query_args.get(search_param, "").strip()

        filtered_rows = rows
        if search_value:
            filtered_rows = [
                row for row in filtered_rows
                if matches_search_query(row, search_value, search_fields, self.query_text_fn)
            ]

        toolbar_filters = []
        for filter_def in filters:
            param = f"{param_prefix}{filter_def['name']}"
            used_params.add(param)
            selected = query_args.get(param, "").strip()
            options = filter_def.get("options")
            if callable(options):
                options = options(rows)
            elif options is None:
                options = filter_option_rows(rows, filter_def["field"], self.query_text_fn)
            options = normalize_toolbar_options(options)

            if selected:
                if "predicate" in filter_def:
                    filtered_rows = [row for row in filtered_rows if filter_def["predicate"](row, selected)]
                else:
                    match_type = filter_def.get("match", "exact")
                    filtered_rows = [
                        row for row in filtered_rows
                        if (
                            self.query_text_fn(selected) in self.query_text_fn(row_value(row, filter_def["field"]))
                            if match_type == "contains"
                            else self.query_text_fn(row_value(row, filter_def["field"])) == self.query_text_fn(selected)
                        )
                    ]

            toolbar_filters.append(
                {
                    "name": param,
                    "label": filter_def["label"],
                    "value": selected,
                    "options": options,
                }
            )

        sort_lookup = {option["value"]: option for option in sort_options}
        selected_sort = query_args.get(sort_param, default_sort).strip() or default_sort
        if selected_sort not in sort_lookup:
            selected_sort = default_sort
        sort_choice = sort_lookup.get(selected_sort)
        if sort_choice and selected_sort != default_sort:
            filtered_rows = sorted(
                filtered_rows,
                key=lambda row: normalize_sort_value(sort_choice["key"](row), self.query_text_fn),
                reverse=bool(sort_choice.get("reverse")),
            )

        persist_params = []
        for key in query_args.keys():
            if key in used_params:
                continue
            for value in query_args.getlist(key):
                if value != "":
                    persist_params.append((key, value))

        has_active_filters = bool(search_value) or any(item["value"] for item in toolbar_filters) or selected_sort != default_sort
        toolbar = {
            "action": request_path,
            "search_param": search_param,
            "search_value": search_value,
            "search_placeholder": search_placeholder,
            "filters": toolbar_filters,
            "sort_param": sort_param,
            "sort_value": selected_sort,
            "sort_options": normalize_toolbar_options(
                [{"value": option["value"], "label": option["label"]} for option in sort_options]
            ),
            "persist_params": persist_params,
            "reset_url": build_reset_url(request_path, persist_params, self.urlencode_fn),
            "has_active_filters": has_active_filters,
            "result_count": len(filtered_rows),
            "total_count": len(rows),
        }
        return filtered_rows, toolbar


def apply_collection_filters(
    rows,
    *,
    query_args,
    request_path,
    query_text_fn,
    urlencode_fn,
    search_fields,
    filters=None,
    sort_options=None,
    default_sort="default",
    search_placeholder="Search",
    param_prefix="",
):
    coordinator = CollectionFilterCoordinator(rows, query_text_fn, urlencode_fn)
    return coordinator.apply(
        query_args=query_args,
        request_path=request_path,
        search_fields=search_fields,
        filters=filters,
        sort_options=sort_options,
        default_sort=default_sort,
        search_placeholder=search_placeholder,
        param_prefix=param_prefix,
    )
