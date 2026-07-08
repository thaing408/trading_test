"""Economic calendar collector."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

import requests

from trading_agent.config import AgentConfig
from trading_agent.models import CalendarEvent, EconomicCalendar

from .base import load_fixture, safe_fetch

FMP_CALENDAR_URL = "https://financialmodelingprep.com/api/v3/economic_calendar"


def _fetch_fmp_calendar(api_key: str) -> List[CalendarEvent]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    resp = requests.get(
        FMP_CALENDAR_URL,
        params={"from": today, "to": today, "apikey": api_key},
        timeout=15,
    )
    resp.raise_for_status()
    events = []
    for row in resp.json()[:20]:
        events.append(
            CalendarEvent(
                time=row.get("date", ""),
                event=row.get("event", ""),
                impact=row.get("impact", "medium"),
                country=row.get("country", "US"),
            )
        )
    return events


def _fixture_calendar() -> EconomicCalendar:
    data = load_fixture("economic_calendar.json")
    events = [CalendarEvent(**e) for e in data.get("events", [])]
    return EconomicCalendar(source="fixture", events=events)


def collect_economic_calendar(config: AgentConfig) -> EconomicCalendar:
    if config.fixture_mode or not config.use_live_data:
        return _fixture_calendar()

    import os

    api_key = os.getenv("FMP_API_KEY", "")
    errors: List[str] = []
    if not api_key:
        errors.append("FMP_API_KEY not set; using fixture calendar fallback")
        cal = _fixture_calendar()
        cal.errors.extend(errors)
        cal.source = "fixture-fallback"
        return cal

    def fetch() -> List[CalendarEvent]:
        return _fetch_fmp_calendar(api_key)

    events = safe_fetch(fetch, [], errors)
    if not events:
        cal = _fixture_calendar()
        cal.errors.extend(errors)
        cal.source = "fixture-fallback"
        return cal
    return EconomicCalendar(source="fmp", events=events, errors=errors)