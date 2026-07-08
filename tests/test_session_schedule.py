"""Tests for session schedule computation."""

from __future__ import annotations

from datetime import date, datetime

from trading_agent.session.schedule import (
    ET,
    MARKET_CLOSE,
    MARKET_OPEN,
    PREMARKET_PUSH,
    compute_session_schedule,
    resolve_trading_date,
    seconds_until,
)


def test_resolve_trading_date_next_weekday_after_close():
    wednesday_after_pt_close = datetime(2026, 7, 8, 17, 0, tzinfo=ET)
    assert resolve_trading_date(now=wednesday_after_pt_close) == date(2026, 7, 9)


def test_compute_session_schedule_for_tomorrow():
    trading_date = date(2026, 7, 9)
    schedule = compute_session_schedule(trading_date, interval_minutes=30)

    assert schedule.trading_date == trading_date
    assert schedule.premarket_push.time() == PREMARKET_PUSH
    assert schedule.market_open.time() == MARKET_OPEN
    assert schedule.market_close.time() == MARKET_CLOSE
    assert schedule.premarket_push < schedule.market_open
    assert schedule.intraday_cycles[0] == schedule.market_open
    assert schedule.intraday_cycles[-1] < schedule.market_close
    assert len(schedule.intraday_cycles) == 13


def test_seconds_until_future_target():
    now = datetime(2026, 7, 8, 20, 0, tzinfo=ET)
    schedule = compute_session_schedule(date(2026, 7, 9), interval_minutes=15)
    delay = seconds_until(schedule.premarket_push, now)
    assert delay > 0
    assert delay == (schedule.premarket_push - now).total_seconds()