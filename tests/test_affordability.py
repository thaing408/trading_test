"""Tests for OMS cash/BP affordability gates (opens + closes)."""

from __future__ import annotations

from trading_agent.export.mac_execute import ReadyOrder
from trading_agent.oms.affordability import (
    check_close_affordability,
    check_open_affordability,
    credit_margin_estimate,
)
from trading_agent.oms.state import OpenLot


def _order(**kw) -> ReadyOrder:
    base = dict(
        order_id="o1",
        symbol="QQQ",
        action="ENTER",
        side="Bullish",
        instrument="options",
        strategy="test",
        setup_id="t",
        entry=10.0,
        stop=9.0,
        target=12.0,
        max_risk_dollars=200.0,
        quantity=1,
        strike_prices=[450.0],
        expiration="2026-08-28",
        defined_risk=True,
    )
    base.update(kw)
    return ReadyOrder(**base)


def test_debit_blocked_when_premium_exceeds_cash():
    order = _order()
    cash = {"fetched": True, "tradable_after_reserve": 500.0}
    r = check_open_affordability(
        order,
        place_path="single_leg_debit",
        account_cash=cash,
        premium_est=800.0,
    )
    assert not r.ok
    assert r.reason.startswith("insufficient_cash:")
    assert r.kind == "debit_open"


def test_debit_ok_when_cash_covers_premium():
    order = _order()
    cash = {"fetched": True, "tradable_after_reserve": 1000.0}
    r = check_open_affordability(
        order,
        place_path="single_leg_debit",
        account_cash=cash,
        premium_est=800.0,
    )
    assert r.ok
    assert r.need == 800.0


def test_credit_open_blocked_without_balances():
    order = _order(side="Bearish", strategy="credit put", defined_risk=True)
    r = check_open_affordability(
        order,
        place_path="credit_ready",
        account_cash={"fetched": False, "error": "down"},
        require_balances=True,
    )
    assert not r.ok
    assert r.reason == "account_cash_unavailable"


def test_credit_open_blocked_when_margin_exceeds_bp():
    order = _order(
        side="short",
        strategy="short put credit",
        max_risk_dollars=2000.0,
        strike_prices=[100.0],
        defined_risk=True,
    )
    cash = {"fetched": True, "tradable_after_reserve": 500.0}
    r = check_open_affordability(
        order, place_path="credit_ready", account_cash=cash
    )
    assert not r.ok
    assert "insufficient_margin" in r.reason


def test_credit_undefined_risk_blocked():
    order = _order(defined_risk=False, max_risk_dollars=100.0)
    cash = {"fetched": True, "tradable_after_reserve": 50_000.0}
    r = check_open_affordability(
        order, place_path="credit_ready", account_cash=cash
    )
    assert not r.ok
    assert r.reason == "credit_not_defined_risk"


def test_sell_to_close_ok_with_balances():
    lot = OpenLot(
        lot_id="l1",
        fingerprint="f",
        symbol="GE",
        instrument="options",
        strategy="x",
        setup_id="x",
        side="Bullish",
        quantity=1,
        entry=3.0,
        stop=2.0,
        target=5.0,
        max_risk_dollars=300,
        fill_entry=3.0,
    )
    cash = {"fetched": True, "tradable_after_reserve": 1000.0}
    r = check_close_affordability(
        lot, instruction="SELL_TO_CLOSE", account_cash=cash
    )
    assert r.ok


def test_buy_to_close_blocked_when_no_cash():
    lot = OpenLot(
        lot_id="l2",
        fingerprint="f2",
        symbol="IWM",
        instrument="options",
        strategy="credit",
        setup_id="x",
        side="short",
        quantity=2,
        entry=1.5,
        stop=0,
        target=0,
        max_risk_dollars=500,
        fill_entry=1.5,
    )
    cash = {"fetched": True, "tradable_after_reserve": 50.0}
    # 1.5 * 100 * 2 * 1.15 = 345
    r = check_close_affordability(
        lot, instruction="BUY_TO_CLOSE", account_cash=cash
    )
    assert not r.ok
    assert "insufficient_cash_to_close" in r.reason


def test_credit_margin_estimate_uses_risk():
    order = _order(max_risk_dollars=250.0)
    assert credit_margin_estimate(order, buffer=1.2) == 300.0
