"""Execution truth: multi-leg safety, reverse on fail, flatten, lifecycle."""

from __future__ import annotations

from trading_agent.export.mac_execute import ReadyOrder
from trading_agent.oms.broker import close_instruction_for_open_leg, order_submitted_ok
from trading_agent.oms.exits import flatten_all_lots, submit_close
from trading_agent.oms.lifecycle import extract_legs_from_broker_response, register_submitted_lot
from trading_agent.oms.multileg import (
    build_multileg_package,
    try_sequential_submit,
)
from trading_agent.oms.state import LotStatus, OpenLot, OmsStore


def _spread_order(**kwargs):
    row = dict(
        order_id="ml1",
        symbol="SPY",
        action="ENTER",
        side="Bullish",
        instrument="options",
        strategy="Bull Put Credit Spread",
        setup_id="options_credit_bull_put",
        entry=1.0,
        stop=2.0,
        target=0.2,
        max_risk_dollars=100.0,
        strike_prices=[500.0, 505.0],
        expiration="2026-08-15",
        quantity=1,
        defined_risk=True,
    )
    row.update(kwargs)
    return ReadyOrder(**row)


def test_build_multileg_package_credit_wings():
    pkg = build_multileg_package(_spread_order())
    assert pkg is not None
    assert len(pkg.legs) == 2
    assert pkg.net_debit_credit == "credit"
    # low strike buy wing, high strike sell body for credit put vertical
    assert pkg.legs[0].instruction == "BUY_TO_OPEN"
    assert pkg.legs[1].instruction == "SELL_TO_OPEN"


def test_sequential_dry_without_flag_ready_only(monkeypatch):
    monkeypatch.delenv("TRADING_AGENT_ALLOW_SEQUENTIAL_MULTILEG", raising=False)
    monkeypatch.delenv("TRADING_AGENT_MULTILEG_LIVE", raising=False)
    order = try_sequential_submit(_spread_order(), live=True, call_mcp=lambda t, p: {})
    assert order.status == "ready"
    assert "multileg_package" in (order.broker_response or {})


def test_sequential_live_wing_first_and_success(monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_MULTILEG_LIVE", "1")
    calls = []

    def mcp(tool, payload):
        calls.append(payload)
        return {"status": "submitted", "dry_run": False}

    order = try_sequential_submit(_spread_order(), live=True, call_mcp=mcp)
    assert order.status == "submitted"
    assert len(calls) == 2
    # wing BUY first
    assert calls[0]["instruction"] == "BUY_TO_OPEN"
    assert calls[1]["instruction"] == "SELL_TO_OPEN"


def test_sequential_live_reverse_on_second_leg_fail(monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_MULTILEG_LIVE", "1")
    n = {"i": 0}

    def mcp(tool, payload):
        n["i"] += 1
        if n["i"] == 1:
            return {"status": "submitted", "dry_run": False}
        if payload.get("instruction") in ("SELL_TO_CLOSE", "BUY_TO_CLOSE"):
            return {"status": "submitted", "dry_run": False}
        return {"error": "reject", "status": "failed"}

    order = try_sequential_submit(_spread_order(), live=True, call_mcp=mcp)
    assert order.status == "failed"
    assert "reversals" in (order.broker_response or {})
    assert order.broker_response["reversals"]


def test_close_instruction_map():
    assert close_instruction_for_open_leg("BUY_TO_OPEN") == "SELL_TO_CLOSE"
    assert close_instruction_for_open_leg("SELL_TO_OPEN") == "BUY_TO_CLOSE"


def test_submit_close_multileg(tmp_path):
    store = OmsStore(root=tmp_path / "oms")
    lot = OpenLot(
        lot_id="x",
        fingerprint="x",
        symbol="SPY",
        instrument="options",
        strategy="Bull Put Credit Spread",
        setup_id="options_credit_bull_put",
        side="Bullish",
        quantity=1,
        entry=1.0,
        stop=2.0,
        target=0.2,
        max_risk_dollars=50,
        status=LotStatus.PROTECTED.value,
        place_path="multi_leg_ready",
        broker_meta={
            "legs": [
                {"occ_symbol": "SPY   260815P00500000", "instruction": "BUY_TO_OPEN", "quantity": 1},
                {"occ_symbol": "SPY   260815P00505000", "instruction": "SELL_TO_OPEN", "quantity": 1},
            ]
        },
    )
    calls = []

    def mcp(tool, payload):
        calls.append(payload)
        return {"status": "submitted", "dry_run": False}

    resp = submit_close(lot, live=True, call_mcp=mcp, reason="test")
    assert resp.get("mode") == "multileg_close"
    assert len(calls) == 2
    instrs = {c["instruction"] for c in calls}
    assert "SELL_TO_CLOSE" in instrs
    assert "BUY_TO_CLOSE" in instrs


def test_register_submitted_lot_legs(tmp_path):
    store = OmsStore(root=tmp_path / "oms")
    lot = OpenLot(
        lot_id="y",
        fingerprint="y",
        symbol="QQQ",
        instrument="options",
        strategy="Debit Spread",
        setup_id="options_debit_call_spread",
        side="Bullish",
        quantity=1,
        entry=2.0,
        stop=1.0,
        target=4.0,
        max_risk_dollars=200,
    )
    legs = [
        {"occ_symbol": "QQQ   260815C00400000", "instruction": "BUY_TO_OPEN", "quantity": 1},
        {"occ_symbol": "QQQ   260815C00410000", "instruction": "SELL_TO_OPEN", "quantity": 1},
    ]
    out = register_submitted_lot(store, lot, broker_response={"status": "submitted"}, legs=legs)
    assert out.status in (LotStatus.OPEN.value, LotStatus.PROTECTED.value)
    assert out.occ_symbol.startswith("QQQ")
    assert store.get_lot("y") is not None


def test_extract_legs_from_response():
    legs = extract_legs_from_broker_response(
        {
            "multileg_package": {
                "legs": [{"occ_symbol": "A", "instruction": "BUY_TO_OPEN", "quantity": 1}]
            },
            "responses": [
                {"leg": {"occ_symbol": "B", "instruction": "SELL_TO_OPEN", "quantity": 1}}
            ],
        }
    )
    assert {leg["occ_symbol"] for leg in legs} == {"A", "B"}


def test_order_submitted_ok():
    assert order_submitted_ok({"status": "submitted"})
    assert order_submitted_ok({"dry_run": True})
    assert not order_submitted_ok({"error": "x"})


def test_flatten_all_lots_dry(tmp_path):
    store = OmsStore(root=tmp_path / "oms")
    lot = OpenLot(
        lot_id="z",
        fingerprint="z",
        symbol="SPY",
        instrument="equity",
        strategy="long",
        setup_id="t",
        side="long",
        quantity=10,
        entry=100,
        stop=95,
        target=110,
        max_risk_dollars=50,
        status=LotStatus.OPEN.value,
    )
    store.upsert_lot(lot)
    store.save()

    def mcp(tool, payload):
        if tool == "get_positions":
            return {"positions": []}
        return {"status": "dry_run", "dry_run": True}

    result = flatten_all_lots(store, live=False, call_mcp=mcp, also_broker_account=True)
    assert "lots" in result
