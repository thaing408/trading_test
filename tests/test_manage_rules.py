"""Tests for multi-day manage rules: trail, EOD 0DTE, min premium."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from trading_agent.oms.manage_rules import (
    calendar_dte,
    early_exit_reasons,
    eod_0dte_flatten_due,
    in_manage_window,
    min_premium_wipe_due,
    update_trail_stop,
)
from trading_agent.oms.state import OpenLot

ET = ZoneInfo("America/New_York")


def _lot(**kwargs) -> OpenLot:
    base = dict(
        lot_id="t1",
        fingerprint="fp",
        symbol="IWM",
        instrument="options",
        strategy="multi",
        setup_id="multi_swing_daily",
        side="Bullish",
        quantity=1,
        entry=300.0,
        stop=290.0,
        target=310.0,
        max_risk_dollars=100,
        status="protected",
        expiration="2026-08-17",
        occ_symbol="IWM   260817C00306000",
    )
    base.update(kwargs)
    return OpenLot(**base)


def test_calendar_dte_from_expiration():
    lot = _lot(expiration="2026-08-17")
    now = datetime(2026, 8, 17, 12, 0, tzinfo=ET)
    assert calendar_dte(lot, now=now) == 0


def test_eod_0dte_before_cutoff(monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_EOD_0DTE_FLATTEN", "1")
    monkeypatch.setenv("TRADING_AGENT_EOD_0DTE_CUTOFF_ET", "15:45")
    lot = _lot(expiration="2026-08-17")
    now = datetime(2026, 8, 17, 14, 0, tzinfo=ET)
    ok, _ = eod_0dte_flatten_due(lot, now=now)
    assert not ok


def test_eod_0dte_after_cutoff(monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_EOD_0DTE_FLATTEN", "1")
    monkeypatch.setenv("TRADING_AGENT_EOD_0DTE_CUTOFF_ET", "15:45")
    lot = _lot(expiration="2026-08-17")
    now = datetime(2026, 8, 17, 15, 50, tzinfo=ET)
    ok, reason = eod_0dte_flatten_due(lot, now=now)
    assert ok and reason == "eod_0dte_flatten"


def test_min_premium_wipe(monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_MIN_PREMIUM_WIPE", "1")
    monkeypatch.setenv("TRADING_AGENT_MIN_OPTION_PREMIUM", "0.05")
    lot = _lot()
    ok, reason = min_premium_wipe_due(lot, option_mark=0.005)
    assert ok and reason.startswith("min_premium_wipe")
    ok2, _ = min_premium_wipe_due(lot, option_mark=0.50)
    assert not ok2


def test_early_exit_prefers_wipe(monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_EOD_0DTE_FLATTEN", "0")
    monkeypatch.setenv("TRADING_AGENT_MIN_PREMIUM_WIPE", "1")
    monkeypatch.setenv("TRADING_AGENT_MIN_OPTION_PREMIUM", "0.05")
    lot = _lot(expiration="2026-08-21")  # not 0DTE
    ok, reason = early_exit_reasons(lot, option_mark=0.01)
    assert ok and "min_premium" in reason


def test_trail_to_breakeven(monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_TRAIL_ENABLED", "1")
    monkeypatch.setenv("TRADING_AGENT_TRAIL_BE_R", "0.5")
    monkeypatch.setenv("TRADING_AGENT_TRAIL_LOCK_PCT", "50")
    lot = _lot(entry=100.0, stop=90.0, target=120.0, side="Bullish")
    # +0.5R = +5 → px 105 triggers BE
    info = update_trail_stop(lot, underlying_price=105.0)
    assert info["trailed"]
    assert lot.stop >= 100.0
    # Further run to 110 locks 50% of +10 = +5 → stop >= 105
    info2 = update_trail_stop(lot, underlying_price=110.0)
    assert info2["trailed"]
    assert lot.stop >= 105.0


def test_in_manage_window(monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_MANAGE_UNTIL_ET", "16:00")
    monkeypatch.setenv("TRADING_AGENT_CONSUMER_FROM_ET", "09:25")
    noon = datetime(2026, 8, 17, 12, 0, tzinfo=ET)  # Monday
    assert in_manage_window(noon)
    late = datetime(2026, 8, 17, 16, 30, tzinfo=ET)
    assert not in_manage_window(late)
