"""Economic calendar collector."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

import requests

from trading_agent.config import AgentConfig
from trading_agent.discord.env import load_project_env
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
    """Live mode never injects fixture events into bias/sentiment (empty if unavailable)."""
    if config.fixture_mode or not config.use_live_data:
        return _fixture_calendar()

    import os

    load_project_env()
    api_key = os.getenv("FMP_API_KEY", "")
    errors: List[str] = []
    if not api_key:
        # Do not invent Jobless Claims / Powell from test fixtures for live desk.
        return EconomicCalendar(
            source="unavailable",
            events=[],
            errors=["FMP_API_KEY not set; calendar omitted from bias (no fixture fill)"],
        )

    def fetch() -> List[CalendarEvent]:
        return _fetch_fmp_calendar(api_key)

    events = safe_fetch(fetch, [], errors)
    if not events:
        if not errors:
            errors.append("No economic calendar events returned for today")
        return EconomicCalendar(source="unavailable", events=[], errors=errors)
    return EconomicCalendar(source="fmp", events=events, errors=errors)