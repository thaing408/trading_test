"""Tests for Pacific-time desk schedule."""

from __future__ import annotations

from datetime import date, datetime

from trading_agent.session.schedule import (
    CIO_APPROVAL_TIME,
    CIO_REVIEW_TIME,
    DESK_CLOSE_PT,
    DESK_OPEN_PT,
    INTELLIGENCE_TIME,
    PERFORMANCE_TIME,
    PREOPEN_TIME,
    PT,
    RESEARCH_TIME,
    DeskPhaseKind,
    compute_desk_schedule,
    resolve_start_phase,
    resolve_trading_date,
    seconds_until,
)


def test_compute_desk_schedule_has_eight_phases():
    trading_date = date(2026, 7, 9)
    schedule = compute_desk_schedule(trading_date, interval_minutes=30)

    assert schedule.phases[0].scheduled_at.time() == INTELLIGENCE_TIME
    assert schedule.phases[1].scheduled_at.time() == RESEARCH_TIME
    assert schedule.phases[2].scheduled_at.time() == CIO_APPROVAL_TIME
    assert schedule.phases[3].scheduled_at.time() == PREOPEN_TIME
    assert schedule.market_open.time() == DESK_OPEN_PT
    assert schedule.market_close.time() == DESK_CLOSE_PT
    assert schedule.phases[5].scheduled_at.time() == PERFORMANCE_TIME
    assert schedule.phases[6].scheduled_at.time() == CIO_REVIEW_TIME
    assert schedule.phases[7].kind == DeskPhaseKind.EVENING_SCAN
    # 18:00 ET on the session date
    assert schedule.phases[7].scheduled_at.astimezone(
        __import__("zoneinfo").ZoneInfo("America/New_York")
    ).hour == 18
    assert schedule.intraday_cycles[0] == schedule.market_open
    assert schedule.intraday_cycles[-1] < schedule.market_close
    assert len(schedule.intraday_cycles) == 13


def test_resolve_start_phase_late_morning_starts_at_intraday():
    schedule = compute_desk_schedule(date(2026, 7, 9), interval_minutes=15)
    now = datetime(2026, 7, 9, 10, 0, tzinfo=PT)
    assert resolve_start_phase(now, schedule) == DeskPhaseKind.INTRADAY


def test_resolve_trading_date_after_pt_close():
    after_close = datetime(2026, 7, 8, 14, 0, tzinfo=PT)
    assert resolve_trading_date(now=after_close) == date(2026, 7, 9)


def test_seconds_until_morning_phase():
    now = datetime(2026, 7, 8, 20, 0, tzinfo=PT)
    schedule = compute_desk_schedule(date(2026, 7, 9), interval_minutes=15)
    delay = seconds_until(schedule.phases[0].scheduled_at, now)
    assert delay > 0