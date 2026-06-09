import os
import re
import html as html_module
import json
import urllib.request
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

# =====================================================================
# Domain Data Containers
# =====================================================================

@dataclass(frozen=True)
class BuhurtEvent:
    name: str
    date: str
    location: str
    summary: str
    url: str
    start_date: str


# =====================================================================
# Core Scraper and Caching Client
# =====================================================================

class BuhurtCalendarClient:
    def __init__(
        self,
        cache_key: str = "buhurt_uk_calendar_cache",
        cache_hours: int = 12,
        events_url: str = "https://example.com/buhurt-calendar",
        fallback_events: Optional[List[Dict[str, Any]]] = None,
    ):
        self.cache_key = cache_key
        self.cache_hours = cache_hours
        self.events_url = events_url
        self.fallback_events = fallback_events or []

    def get_calendar_events(self, conn, is_testing: bool = False) -> List[BuhurtEvent]:
        # 1. Try to load from SQLite cache
        cached_payload = None
        refreshed_at = None
        try:
            row = conn.execute(
                "SELECT payload, refreshed_at FROM external_cache WHERE key=?",
                (self.cache_key,),
            ).fetchone()
            if row:
                cached_payload = json.loads(row["payload"])
                refreshed_at = datetime.fromisoformat(row["refreshed_at"])
        except Exception:
            pass

        # 2. Check if cache is fresh
        cache_is_fresh = False
        if refreshed_at is not None:
            cache_is_fresh = (datetime.utcnow() - refreshed_at) < timedelta(hours=self.cache_hours)

        if cached_payload and cache_is_fresh:
            return [BuhurtEvent(**ev) for ev in cached_payload]

        if is_testing:
            events_list = cached_payload if cached_payload else self._load_fallback_events()
            return [BuhurtEvent(**ev) for ev in events_list]

        # 3. Cache is stale/empty and not testing: fetch from web
        try:
            fetched_events = self._fetch_and_parse()
            if fetched_events:
                self._save_to_cache(conn, fetched_events)
                return fetched_events
        except Exception:
            # On network/parsing errors, fallback gracefully to cached copy or fallback list
            pass

        events_list = cached_payload if cached_payload else self._load_fallback_events()
        try:
            self._save_to_cache(conn, [BuhurtEvent(**ev) for ev in events_list])
        except Exception:
            pass
        return [BuhurtEvent(**ev) for ev in events_list]

    def get_upcoming_tournaments(self, conn, limit: int = 6, is_testing: bool = False) -> List[BuhurtEvent]:
        today = datetime.utcnow().date().isoformat()
        events = self.get_calendar_events(conn, is_testing=is_testing)
        upcoming = [e for e in events if e.start_date >= today]
        return upcoming[:limit]

    def sync_banners(self, conn, events: List[BuhurtEvent], active_leagues: List[Any]) -> int:
        synced_count = 0
        for league in active_leagues:
            league_id = league["id"] if isinstance(league, dict) or hasattr(league, "keys") else league[0]
            for event in events:
                event_name = event.name.strip()
                event_date = event.start_date or event.date.strip()
                if not event_name or not event_date:
                    continue
                source_url = event.url
                slug_name = "-".join(event_name.lower().split())
                external_key = f"{source_url or 'calendar'}#{event_date}:{slug_name}"
                existing = conn.execute(
                    """
                    SELECT id
                    FROM event_banners
                    WHERE league_id=?
                      AND (
                        (external_key IS NOT NULL AND external_key=?)
                        OR (event_name=? AND event_date=?)
                      )
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (league_id, external_key, event_name, event_date),
                ).fetchone()
                params = (
                    league_id,
                    event_name,
                    event_date,
                    event.location,
                    source_url,
                    event.summary,
                    external_key,
                )
                if existing:
                    conn.execute(
                        """
                        UPDATE event_banners
                        SET event_name=?,
                            event_date=?,
                            location=?,
                            source_url=?,
                            summary=?,
                            source_kind='calendar',
                            external_key=?
                        WHERE id=?
                        """,
                        (event_name, event_date, event.location, source_url, event.summary, external_key, existing["id"]),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO event_banners(
                            league_id,event_name,event_date,location,source_url,summary,source_kind,external_key
                        ) VALUES(?,?,?,?,?,?, 'calendar', ?)
                        """,
                        params,
                    )
                    synced_count += 1
        conn.commit()
        return synced_count

    def _load_fallback_events(self) -> List[Dict[str, Any]]:
        events = []
        for event in self.fallback_events:
            copy = dict(event)
            start_date, _ = parse_event_date_range(copy["date"])
            copy["start_date"] = start_date or "9999-12-31"
            events.append(copy)
        return sorted(events, key=lambda event: event["start_date"])

    def _fetch_and_parse(self) -> List[BuhurtEvent]:
        request = urllib.request.Request(
            self.events_url,
            headers={"User-Agent": "InvictaFantasyLeague/1.0 (+local tournament cache)"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            html = response.read().decode("utf-8", errors="ignore")

        heading_matches = list(re.finditer(r"<h[1-6][^>]*>(.*?)</h[1-6]>", html, flags=re.IGNORECASE | re.DOTALL))
        events = []
        seen = set()
        for index, match in enumerate(heading_matches):
            title = self._strip_html(match.group(1))
            parsed = re.match(r"(.+?)\s+-\s+(.+?)\s+(.+?\d{4})$", title)
            if not parsed:
                continue
            name, location, raw_date = [part.strip() for part in parsed.groups()]
            start_date, display_date = parse_event_date_range(raw_date)
            if not start_date:
                continue
            key = (name.lower(), start_date)
            if key in seen:
                continue
            seen.add(key)

            next_start = heading_matches[index + 1].start() if index + 1 < len(heading_matches) else min(len(html), match.end() + 1200)
            section = html[match.end():next_start]
            urls = re.findall(r"https://www\.buhurtinternational\.com/tournament/[^\s\"'<]+", section)
            events.append(
                BuhurtEvent(
                    name=name,
                    date=display_date,
                    location=location,
                    summary="Upcoming UK buhurt tournament listed by MCSA GB.",
                    url=urls[0] if urls else self.events_url,
                    start_date=start_date,
                )
            )
        events.sort(key=lambda event: event.start_date)
        return events

    def _strip_html(self, value: str) -> str:
        text = re.sub(r"<[^>]+>", " ", value)
        return " ".join(html_module.unescape(text).split())

    def _save_to_cache(self, conn, events: List[BuhurtEvent]):
        serialized = [asdict(e) for e in events]
        now_iso = datetime.utcnow().replace(microsecond=0).isoformat()
        conn.execute(
            """
            INSERT INTO external_cache(key,payload,refreshed_at)
            VALUES(?,?,?)
            ON CONFLICT(key) DO UPDATE SET payload=excluded.payload, refreshed_at=excluded.refreshed_at
            """,
            (self.cache_key, json.dumps(serialized), now_iso),
        )
        conn.commit()


# =====================================================================
# Legacy Compatibility Wrappers & Helpers
# =====================================================================

def parse_event_date_range(raw_date, *, os_name=None):
    if os_name is None:
        os_name = os.name
    text = " ".join(raw_date.replace(",", " ").split())
    match = re.search(r"(\d{1,2})(?:st|nd|rd|th)?(?:\s*(?:-|&|and)\s*(\d{1,2})(?:st|nd|rd|th)?)?\s+([A-Za-z]+)\s+(\d{4})", text)
    if not match:
        return None, raw_date
    start_day, end_day, month_name, year = match.groups()
    try:
        start_date = datetime.strptime(f"{start_day} {month_name} {year}", "%d %B %Y").date()
    except ValueError:
        return None, raw_date
    display = start_date.strftime("%-d %B %Y") if os_name != "nt" else start_date.strftime("%#d %B %Y")
    if end_day:
        display = f"{int(start_day)}-{int(end_day)} {month_name} {year}"
    return start_date.isoformat(), display


def strip_html(value, unescape_fn=None):
    if unescape_fn is None:
        unescape_fn = html_module.unescape
    text = re.sub(r"<[^>]+>", " ", value)
    return " ".join(unescape_fn(text).split())


def fetch_buhurt_uk_tournaments(
    *,
    events_url,
    request_cls=None,
    urlopen_fn=None,
    parse_event_date_range_fn=None,
    strip_html_fn=None,
):
    client = BuhurtCalendarClient(events_url=events_url)
    events = client._fetch_and_parse()
    return [asdict(e) for e in events]


def fallback_buhurt_uk_tournaments(fallback_events=None, parse_event_date_range_fn=None):
    if fallback_events is None:
        from app import FALLBACK_BUHURT_UK_TOURNAMENTS
        fallback_events = FALLBACK_BUHURT_UK_TOURNAMENTS
    client = BuhurtCalendarClient(fallback_events=fallback_events)
    return client._load_fallback_events()


def cached_tournament_payload(conn, cache_key, json_module=None):
    if json_module is None:
        json_module = json
    row = conn.execute("SELECT payload, refreshed_at FROM external_cache WHERE key=?", (cache_key,)).fetchone()
    if not row:
        return None, None
    try:
        return json_module.loads(row["payload"]), datetime.fromisoformat(row["refreshed_at"])
    except (TypeError, ValueError):
        return None, None


def save_tournament_cache(conn, cache_key, events, now_iso_fn=None, json_module=None):
    if json_module is None:
        json_module = json
    if now_iso_fn is None:
        def now_iso_fn(): return datetime.utcnow().replace(microsecond=0).isoformat()
    conn.execute(
        """
        INSERT INTO external_cache(key,payload,refreshed_at)
        VALUES(?,?,?)
        ON CONFLICT(key) DO UPDATE SET payload=excluded.payload, refreshed_at=excluded.refreshed_at
        """,
        (cache_key, json_module.dumps(events), now_iso_fn()),
    )
    conn.commit()


def calendar_buhurt_uk_tournaments(
    conn,
    *,
    cache_key,
    cache_hours,
    app_testing,
    cached_tournament_payload_fn=None,
    fallback_buhurt_uk_tournaments_fn=None,
    fetch_buhurt_uk_tournaments_fn=None,
    save_tournament_cache_fn=None,
    handled_errors=None,
):
    client = BuhurtCalendarClient(cache_key=cache_key, cache_hours=cache_hours)
    events = client.get_calendar_events(conn, is_testing=app_testing)
    return [asdict(e) for e in events]


def upcoming_buhurt_uk_tournaments(
    conn,
    *,
    calendar_buhurt_uk_tournaments_fn=None,
    limit=6,
):
    client = BuhurtCalendarClient()
    events = client.get_upcoming_tournaments(conn, limit=limit)
    return [asdict(e) for e in events]


def sync_calendar_event_banners(conn, calendar_events, *, active_leagues):
    client = BuhurtCalendarClient()
    events = [BuhurtEvent(**e) for e in calendar_events]
    return client.sync_banners(conn, events, active_leagues)
