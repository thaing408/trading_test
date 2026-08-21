"""Auto-desk win-rate gates."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from trading_agent.oms.wr_desk import (
    apply_payoff,
    dte_ok,
    evaluate_wr_enter,
    process_session_ok,
    setup_allowed,
    time_stop_due,
)


@pytest.fixture(autouse=True)
def _wr_on(monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_WR_DESK", "1")
    monkeypatch.setenv("TRADING_AGENT_WR_DESK_TEST", "1")
    monkeypatch.setenv("TRADING_AGENT_WR_TAPE", "0")


def test_chop_and_light_block_session():
    ok, reason = process_session_ok(bias="trade", regime="chop / range")
    assert not ok and "chop" in reason
    ok, reason = process_session_ok(bias="light", regime="trend_up")
    assert not ok and "light" in reason
    ok, reason = process_session_ok(bias="trade", regime="trend_up")
    assert ok, reason


def test_tape_vix_blocks():
    tape = {
        "ok": True,
        "push": False,
        "ma_ok": True,
        "vix_ok": False,
        "vix": 24.0,
    }
    ok, reason = process_session_ok(bias="trade", regime="trend", tape=tape)
    assert not ok and "vix" in reason


def test_setup_pullback_only():
    fvg = SimpleNamespace(
        setup_id="multi_fvg",
        strategy="Multi-method long call (fvg)",
        side="Bullish",
        method_tags=["multi_method", "fvg"],
    )
    orb = SimpleNamespace(
        setup_id="multi_orb_vwap",
        strategy="Multi-method long call (orb_vwap)",
        side="Bullish",
        method_tags=["orb_vwap"],
    )
    put = SimpleNamespace(
        setup_id="multi_fvg",
        strategy="long put",
        side="PUT",
        method_tags=["fvg"],
    )
    assert setup_allowed(fvg)[0]
    assert not setup_allowed(orb)[0]
    assert not setup_allowed(put)[0]


def test_dte_blocks_0dte():
    ok, reason = dte_ok("QQQ", 0, tape_push=True)
    assert not ok
    ok, _ = dte_ok("NVDA", 5)
    assert ok


def test_payoff_is_two_r():
    assert apply_payoff(100, 98, bullish=True) == 104.0
    assert apply_payoff(100, 102, bullish=False) == 96.0


def test_time_stop():
    lot = SimpleNamespace(
        opened_at=(datetime.now(timezone.utc) - timedelta(minutes=90)).isoformat()
    )
    ok, reason = time_stop_due(lot)
    assert ok and "wr_time_stop" in reason


def test_evaluate_wr_enter_combo():
    order = SimpleNamespace(
        setup_id="multi_fvg",
        strategy="fvg call",
        side="Bullish",
        method_tags=["fvg"],
        symbol="NVDA",
        expiration="2099-01-01",
        bid_ask_spread_pct=3.0,
    )
    ok, reason = evaluate_wr_enter(
        order, bias="trade", regime="trend_up", dte=7
    )
    assert ok, reason
    order.bid_ask_spread_pct = 20.0
    ok, reason = evaluate_wr_enter(
        order, bias="trade", regime="trend_up", dte=7
    )
    assert not ok and "spread" in reason
