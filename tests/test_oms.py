"""OMS: kill switch, pretrade, protect, multileg, pipeline (fail-closed)."""

from __future__ import annotations

from pathlib import Path

from trading_agent.export.mac_execute import ReadyOrder
from trading_agent.oms.kill_switch import clear_kill_switch, is_killed, set_kill_switch
from trading_agent.oms.multileg import build_multileg_package
from trading_agent.oms.broker import parse_tradable_cash
from trading_agent.oms.pretrade import (
    PretradeConfig,
    estimate_order_cash_required,
    evaluate_pretrade,
)
from trading_agent.oms.protect import should_exit_lot
from trading_agent.oms.state import LotStatus, OpenLot, OmsStore


def test_kill_switch_roundtrip(tmp_path, monkeypatch):
    path = tmp_path / "kill.json"
    monkeypatch.setenv("TRADING_AGENT_KILL_SWITCH_FILE", str(path))
    monkeypatch.delenv("TRADING_AGENT_KILL_SWITCH", raising=False)
    clear_kill_switch()
    assert not is_killed()
    set_kill_switch("test halt", flatten=True)
    assert is_killed()
    clear_kill_switch()
    assert not is_killed()


def test_pretrade_blocks_on_max_open(tmp_path):
    store = OmsStore(root=tmp_path / "oms")
    for i in range(3):
        store.upsert_lot(
            OpenLot(
                lot_id=f"lot{i}",
                fingerprint=f"fp{i}",
                symbol=f"S{i}",
                instrument="options",
                strategy="test",
                setup_id="t",
                side="long",
                quantity=1,
                entry=10,
                stop=9,
                target=12,
                max_risk_dollars=100,
                status=LotStatus.OPEN.value,
            )
        )
    store.save()
    order = ReadyOrder(
        order_id="new",
        symbol="ZZZ",
        action="ENTER",
        side="long",
        instrument="options",
        strategy="x",
        setup_id="x",
        entry=1,
        stop=0.5,
        target=2,
        max_risk_dollars=50,
        defined_risk=True,
    )
    ok, reason = evaluate_pretrade(
        order,
        store,
        config=PretradeConfig(
            max_open_lots=3,
            max_open_risk_dollars=10_000,
            require_process_gate=False,
        ),
    )
    assert not ok and reason == "max_open_lots"


def test_pretrade_blocks_same_symbol_after_two_round_trips(tmp_path):
    """2 round trips block re-entry on same ticker only — other symbols OK."""
    store = OmsStore(root=tmp_path / "oms")
    store.ensure_day("2026-08-12")
    store.record_round_trip("NVDA")
    store.record_round_trip("NVDA")
    store.save()
    cfg = PretradeConfig(
        max_open_lots=10,
        max_open_risk_dollars=50_000,
        max_round_trips_per_symbol_per_day=2,
        max_round_trips_per_day=0,  # no global day halt
        require_process_gate=False,
    )
    blocked = ReadyOrder(
        order_id="nvda3",
        symbol="NVDA",
        action="ENTER",
        side="long",
        instrument="options",
        strategy="x",
        setup_id="x",
        entry=1,
        stop=0.5,
        target=2,
        max_risk_dollars=50,
        defined_risk=True,
    )
    ok, reason = evaluate_pretrade(blocked, store, config=cfg)
    assert not ok
    assert "max_round_trips_per_symbol" in reason
    assert "NVDA" in reason

    other = ReadyOrder(
        order_id="amd1",
        symbol="AMD",
        action="ENTER",
        side="long",
        instrument="options",
        strategy="x",
        setup_id="x",
        entry=1,
        stop=0.5,
        target=2,
        max_risk_dollars=50,
        defined_risk=True,
    )
    ok2, reason2 = evaluate_pretrade(other, store, config=cfg)
    assert ok2, reason2


def test_pretrade_daily_loss(tmp_path):
    store = OmsStore(root=tmp_path / "oms")
    store.add_realized_pnl(-600)
    order = ReadyOrder(
        order_id="n",
        symbol="A",
        action="ENTER",
        side="long",
        instrument="equity",
        strategy="x",
        setup_id="x",
        entry=100,
        stop=99,
        target=110,
        max_risk_dollars=50,
    )
    ok, reason = evaluate_pretrade(
        order,
        store,
        config=PretradeConfig(
            max_day_loss_dollars=500,
            max_open_lots=10,
            require_process_gate=False,
        ),
    )
    assert not ok and reason == "daily_loss_halt"


def test_should_exit_lot_bullish():
    lot = OpenLot(
        lot_id="1",
        fingerprint="1",
        symbol="QQQ",
        instrument="equity",
        strategy="long",
        setup_id="t",
        side="long",
        quantity=10,
        entry=100,
        stop=95,
        target=110,
        max_risk_dollars=50,
        status=LotStatus.PROTECTED.value,
    )
    assert should_exit_lot(lot, mark_price=94)[0] is True
    assert should_exit_lot(lot, mark_price=111)[1] == "profit_target"
    assert should_exit_lot(lot, mark_price=100)[0] is False


def test_build_multileg_package_ic():
    order = ReadyOrder(
        order_id="ic",
        symbol="SPY",
        action="ENTER",
        side="Neutral",
        instrument="options",
        strategy="Iron Condor",
        setup_id="options_credit_iron_condor",
        entry=5,
        stop=10,
        target=1,
        max_risk_dollars=100,
        strike_prices=[400.0, 405.0, 420.0, 425.0],
        expiration="2026-08-15",
        quantity=1,
        defined_risk=True,
    )
    pkg = build_multileg_package(order)
    assert pkg is not None
    assert len(pkg.legs) == 4
    assert pkg.net_debit_credit == "credit"
    assert all(leg.occ_symbol for leg in pkg.legs)


def test_oms_store_processed(tmp_path):
    store = OmsStore(root=tmp_path / "oms")
    assert not store.is_processed("abc")
    store.mark_processed("abc")
    store.save()
    store2 = OmsStore(root=tmp_path / "oms")
    assert store2.is_processed("abc")


def _sample_order(symbol: str = "NVDA") -> ReadyOrder:
    return ReadyOrder(
        order_id="pg1",
        symbol=symbol,
        action="ENTER",
        side="long",
        instrument="options",
        strategy="call",
        setup_id="x",
        entry=1.0,
        stop=0.5,
        target=2.0,
        max_risk_dollars=50,
        defined_risk=True,
    )


def test_pretrade_process_gate_blocks_unset_bias(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_PROCESS_DIR", str(tmp_path / "process"))
    store = OmsStore(root=tmp_path / "oms")
    order = _sample_order()
    detail: dict = {}
    ok, reason = evaluate_pretrade(
        order,
        store,
        config=PretradeConfig(
            require_process_gate=True,
            process_probe_desk=False,
            max_open_lots=10,
            max_open_risk_dollars=10_000,
        ),
        process_detail=detail,
    )
    assert not ok
    assert reason.startswith("process_bias_unset") or "process_step" in reason


def test_pretrade_process_gate_blocks_cash(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_PROCESS_DIR", str(tmp_path / "process"))
    from trading_agent.runbook import process as proc

    day = None
    proc.set_regime("cash", regime="risk-off", reason="halt", day=day)
    store = OmsStore(root=tmp_path / "oms")
    ok, reason = evaluate_pretrade(
        _sample_order(),
        store,
        config=PretradeConfig(
            require_process_gate=True,
            process_probe_desk=False,
            max_open_lots=10,
            max_open_risk_dollars=10_000,
        ),
    )
    assert not ok
    assert reason == "process_cash_bias"


def test_pretrade_process_gate_allows_when_steps_complete(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_PROCESS_DIR", str(tmp_path / "process"))
    from trading_agent.runbook import process as proc

    proc.set_regime("trade", regime="bull", reason="trend ok")
    proc.upsert_focus_list(["NVDA", "AMD"])
    proc.upsert_trade_card(
        "NVDA",
        trigger="breakout",
        stop="2%",
        size_risk="1R",
        exit_plan="trail",
    )
    store = OmsStore(root=tmp_path / "oms")
    detail: dict = {}
    ok, reason = evaluate_pretrade(
        _sample_order("NVDA"),
        store,
        config=PretradeConfig(
            require_process_gate=True,
            process_probe_desk=False,
            process_min_step_score=50.0,
            max_open_lots=10,
            max_open_risk_dollars=10_000,
        ),
        process_detail=detail,
    )
    assert ok, reason
    assert reason == ""
    assert detail.get("ok") is True


def test_parse_tradable_cash_prefers_available():
    resp = {
        "balances": {
            "cash_available": 108.75,
            "buying_power": 435.0,
            "cash_balance": 0.0,
        }
    }
    assert parse_tradable_cash(resp, prefer="cash_available") == 108.75
    assert parse_tradable_cash(resp, prefer="buying_power") == 435.0
    assert parse_tradable_cash(resp, prefer="min") == 108.75


def test_estimate_order_cash_prefers_premium():
    order = ReadyOrder(
        order_id="p",
        symbol="AMD",
        action="ENTER",
        side="Bullish",
        instrument="options",
        strategy="x",
        setup_id="x",
        entry=100,
        stop=90,
        target=120,
        max_risk_dollars=50,
        quantity=1,
    )
    assert estimate_order_cash_required(order, premium_dollars=1395.0) == 1395.0
    # fallback uses risk * buffer
    assert estimate_order_cash_required(order, buffer=1.05) == 52.5


def test_pretrade_blocks_insufficient_cash(tmp_path):
    store = OmsStore(root=tmp_path / "oms")
    order = ReadyOrder(
        order_id="rich",
        symbol="AMAT",
        action="ENTER",
        side="Bullish",
        instrument="options",
        strategy="x",
        setup_id="x",
        entry=500,
        stop=400,
        target=550,
        max_risk_dollars=500,
        quantity=2,
        defined_risk=True,
    )
    ok, reason = evaluate_pretrade(
        order,
        store,
        config=PretradeConfig(
            require_process_gate=False,
            max_open_lots=10,
            max_open_risk_dollars=50_000,
            require_account_cash=True,
            min_cash_reserve=25,
        ),
        buying_power=83.75,  # ~108 cash - 25 reserve
        cash_required=2790.0,  # 2x ~$13.95 ask * 100
    )
    assert not ok
    assert reason.startswith("insufficient_cash:")


def test_pretrade_allows_when_cash_covers(tmp_path):
    store = OmsStore(root=tmp_path / "oms")
    order = ReadyOrder(
        order_id="cheap",
        symbol="TLT",
        action="ENTER",
        side="Bearish",
        instrument="options",
        strategy="x",
        setup_id="x",
        entry=82,
        stop=83,
        target=80,
        max_risk_dollars=50,
        quantity=1,
        defined_risk=True,
    )
    ok, reason = evaluate_pretrade(
        order,
        store,
        config=PretradeConfig(
            require_process_gate=False,
            max_open_lots=10,
            max_open_risk_dollars=50_000,
            require_account_cash=True,
        ),
        buying_power=200.0,
        cash_required=5.25,  # $0.05 put * 100 * 1.05
    )
    assert ok, reason


def test_pretrade_blocks_missing_cash_when_required(tmp_path):
    store = OmsStore(root=tmp_path / "oms")
    order = ReadyOrder(
        order_id="nocash",
        symbol="SPY",
        action="ENTER",
        side="Bullish",
        instrument="options",
        strategy="x",
        setup_id="x",
        entry=500,
        stop=490,
        target=510,
        max_risk_dollars=100,
        quantity=1,
        defined_risk=True,
    )
    ok, reason = evaluate_pretrade(
        order,
        store,
        config=PretradeConfig(
            require_process_gate=False,
            require_account_cash=True,
            max_open_lots=10,
            max_open_risk_dollars=50_000,
        ),
        buying_power=None,
        cash_required=100.0,
    )
    assert not ok and reason == "account_cash_unavailable"
