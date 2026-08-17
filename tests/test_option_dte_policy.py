"""Dual-path option DTE: 0DTE indexes vs min 3 DTE equities."""

from __future__ import annotations

from datetime import date

from trading_agent.export.option_dte_policy import (
    calendar_dte,
    dte_allowed,
    min_dte_for_symbol,
    pick_option_expiration,
)


def test_index_0dte_on_weekday():
    monday = date(2026, 8, 17)
    assert monday.weekday() == 0
    for sym in ("SPY", "QQQ", "IWM"):
        assert min_dte_for_symbol(sym) == 0
        assert pick_option_expiration(sym, from_day=monday) == monday
        ok, why, dte = dte_allowed(sym, monday, asof=monday)
        assert ok and dte == 0 and why == ""


def test_equity_min_dte_gt_2():
    monday = date(2026, 8, 17)
    assert min_dte_for_symbol("AAPL") == 3
    assert min_dte_for_symbol("NVDA") == 3
    exp = pick_option_expiration("AAPL", from_day=monday)
    assert calendar_dte(exp, asof=monday) >= 3
    ok, why, dte = dte_allowed("AAPL", monday, asof=monday)
    assert not ok and "dte_too_short" in why


def test_index_weekend_rolls_to_session():
    saturday = date(2026, 8, 15)
    exp = pick_option_expiration("SPY", from_day=saturday)
    assert exp.weekday() < 5
    assert exp >= saturday
