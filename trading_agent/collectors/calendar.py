"""Economic calendar collector."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import List

import requests

from trading_agent.config import AgentConfig
from trading_agent.discord.env import load_project_env
from trading_agent.models import CalendarEvent, EconomicCalendar

from .base import load_fixture, safe_fetch

FMP_ECONOMIC_CALENDAR_URL = "https://financialmodelingprep.com/stable/economic-calendar"
FMP_EARNINGS_CALENDAR_URL = "https://financialmodelingprep.com/stable/earnings-calendar"


def _fmp_get(url: str, api_key: str, params: dict | None = None) -> requests.Response:
    query = dict(params or {})
    query["apikey"] = api_key
    return requests.get(url, params=query, timeout=15)


def _parse_economic_rows(rows: list[dict]) -> List[CalendarEvent]:
    events: List[CalendarEvent] = []
    for row in rows[:20]:
        events.append(
            CalendarEvent(
                time=row.get("date") or row.get("time") or "",
                event=row.get("event") or row.get("name") or "",
                impact=(row.get("impact") or "medium").lower(),
                country=row.get("country") or "US",
            )
        )
    return events


def _fetch_fmp_economic_calendar(api_key: str) -> List[CalendarEvent]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    resp = _fmp_get(
        FMP_ECONOMIC_CALENDAR_URL,
        api_key,
        {"from": today, "to": today},
    )
    if resp.status_code == 402:
        raise PermissionError(
            "FMP economic calendar requires a paid plan (Starter+); using earnings calendar fallback"
        )
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, list):
        return []
    return _parse_economic_rows(payload)


def _fetch_fmp_earnings_calendar(api_key: str) -> List[CalendarEvent]:
    """Free-tier fallback: today's earnings releases as high-impact desk catalysts."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    resp = _fmp_get(
        FMP_EARNINGS_CALENDAR_URL,
        api_key,
        {"from": today, "to": today},
    )
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, list):
        return []

    events: List[CalendarEvent] = []
    for row in payload[:15]:
        symbol = (row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        eps_actual = row.get("epsActual")
        eps_est = row.get("epsEstimated")
        if eps_actual is not None and eps_est is not None:
            detail = f"{symbol} earnings (EPS {eps_actual} vs est {eps_est})"
        else:
            detail = f"{symbol} earnings release"
        events.append(
            CalendarEvent(
                time=row.get("date") or today,
                event=detail,
                impact="high",
                country="US",
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

    load_project_env()
    api_key = os.getenv("FMP_API_KEY", "").strip()
    errors: List[str] = []
    if not api_key:
        return EconomicCalendar(
            source="unavailable",
            events=[],
            errors=["FMP_API_KEY not set; calendar omitted from bias (no fixture fill)"],
        )

    def fetch() -> List[CalendarEvent]:
        try:
            events = _fetch_fmp_economic_calendar(api_key)
            if events:
                return events
        except PermissionError as exc:
            errors.append(str(exc))
        except requests.HTTPError as exc:
            errors.append(f"FMP economic calendar HTTP error: {exc}")

        earnings = _fetch_fmp_earnings_calendar(api_key)
        if earnings:
            errors.append("Macro calendar unavailable on current FMP plan; using today's earnings calendar")
            return earnings
        return []

    events = safe_fetch(fetch, [], errors)
    if not events:
        if not errors:
            errors.append("No economic or earnings calendar events returned for today")
        return EconomicCalendar(source="unavailable", events=[], errors=errors)

    source = "fmp-earnings" if any("earnings calendar fallback" in e for e in errors) else "fmp"
    return EconomicCalendar(source=source, events=events, errors=errors)