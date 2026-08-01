"""OMS: kill switch, pretrade, protect, multileg, pipeline (fail-closed)."""

from __future__ import annotations

from pathlib import Path

from trading_agent.export.mac_execute import ReadyOrder
from trading_agent.oms.kill_switch import clear_kill_switch, is_killed, set_kill_switch
from trading_agent.oms.multileg import build_multileg_package
from trading_agent.oms.pretrade import PretradeConfig, evaluate_pretrade
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
        order, store, config=PretradeConfig(max_open_lots=3, max_open_risk_dollars=10_000)
    )
    assert not ok and reason == "max_open_lots"


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
        order, store, config=PretradeConfig(max_day_loss_dollars=500, max_open_lots=10)
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
