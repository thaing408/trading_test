"""Tests for macOS auto-trade book → ready orders (fail-closed)."""

from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from trading_agent.export.mac_execute import (
    ReadyOrder,
    build_ready_orders,
    classify_place_path,
    entry_fingerprint,
    format_checklist,
    format_occ_symbol,
    in_consumer_window,
    in_qt_window,
    infer_call_put,
    parse_expiration_date,
    submit_order,
    validate_enter,
)
from datetime import date


def _good_options_entry(**overrides):
    row = {
        "symbol": "TSLA",
        "action": "ENTER",
        "side": "Neutral",
        "strategy": "Iron Condor",
        "setup_id": "options_credit_iron_condor",
        "entry": 250.0,
        "stop": 266.0,
        "target": 156.0,
        "max_risk_dollars": 50.0,
        "strike_prices": [235.0, 242.5, 257.5, 265.0],
        "expiration": "2026-08-15",
        "defined_risk": True,
        "instrument": "options",
        "confidence": 70.0,
        "auto_trade_eligible": True,
        "checklist_passed": True,
        "edge_complete": True,
    }
    row.update(overrides)
    return row


def test_validate_enter_ok():
    ok, reason = validate_enter(_good_options_entry())
    assert ok and reason == ""


def test_validate_enter_fail_closed_incomplete():
    ok, reason = validate_enter(_good_options_entry(stop=0))
    assert not ok and reason == "incomplete_risk_package"


def test_validate_enter_missing_strikes_options():
    ok, reason = validate_enter(_good_options_entry(strike_prices=[]))
    assert not ok and reason == "missing_strikes"


def test_validate_enter_not_auto_eligible():
    ok, reason = validate_enter(_good_options_entry(auto_trade_eligible=False))
    assert not ok and reason == "not_auto_eligible"


def test_build_ready_orders_skips_cash_and_bad():
    books = [
        {
            "_path": "/tmp/auto_trade_book.json",
            "stay_in_cash": False,
            "entries": [
                _good_options_entry(),
                _good_options_entry(symbol="BAD", entry=0, strike_prices=[1]),
            ],
        }
    ]
    orders = build_ready_orders(books)
    assert len(orders) == 2
    good = [o for o in orders if o.symbol == "TSLA"][0]
    bad = [o for o in orders if o.symbol == "BAD"][0]
    assert good.status == "ready"
    assert bad.status == "skipped"
    assert bad.skip_reason == "incomplete_risk_package"


def test_build_ready_orders_respects_processed():
    entry = _good_options_entry()
    fp = entry_fingerprint(entry, "/tmp/auto_trade_book.json")
    books = [
        {
            "_path": "/tmp/auto_trade_book.json",
            "stay_in_cash": False,
            "entries": [entry],
        }
    ]
    orders = build_ready_orders(books, processed={fp})
    assert orders[0].status == "skipped"
    assert orders[0].skip_reason == "already_processed"


def test_format_checklist_mentions_status():
    books = [
        {
            "_path": "/tmp/b.json",
            "stay_in_cash": False,
            "entries": [_good_options_entry()],
        }
    ]
    orders = build_ready_orders(books)
    text = format_checklist(orders, live=False)
    assert "TSLA" in text
    assert "ready" in text.lower() or "ENTER" in text


def test_qt_window_bounds():
    ET = ZoneInfo("America/New_York")
    open_ts = datetime(2026, 7, 16, 9, 35, tzinfo=ET)  # Thursday
    assert in_qt_window(open_ts)
    early = datetime(2026, 7, 16, 9, 0, tzinfo=ET)
    assert not in_qt_window(early)
    weekend = datetime(2026, 7, 18, 9, 35, tzinfo=ET)  # Saturday
    assert not in_qt_window(weekend)


def test_consumer_window_bounds():
    ET = ZoneInfo("America/New_York")
    ok = datetime(2026, 7, 16, 10, 0, tzinfo=ET)
    assert in_consumer_window(ok)
    late = datetime(2026, 7, 16, 12, 0, tzinfo=ET)
    assert not in_consumer_window(late)


def test_underlying_no_strikes_ok():
    ok, reason = validate_enter(
        {
            "symbol": "QQQ",
            "action": "ENTER",
            "entry": 500.0,
            "stop": 495.0,
            "target": 510.0,
            "max_risk_dollars": 200.0,
            "instrument": "underlying",
            "defined_risk": True,
        }
    )
    assert ok and reason == ""


def _ready(**overrides) -> ReadyOrder:
    base = dict(
        order_id="x",
        symbol="QQQ",
        action="ENTER",
        side="long",
        instrument="options",
        strategy="Long Call",
        setup_id="options_debit_call",
        entry=5.0,
        stop=480.0,
        target=520.0,
        max_risk_dollars=100.0,
        strike_prices=[500.0],
        expiration="2026-08-15",
        quantity=1,
        defined_risk=True,
        confidence=70.0,
        source_book="/tmp/b.json",
        status="ready",
    )
    base.update(overrides)
    return ReadyOrder(**base)


def test_format_occ_symbol():
    occ = format_occ_symbol("QQQ", date(2026, 8, 15), "CALL", 500.0)
    assert occ == "QQQ   260815C00500000"
    put = format_occ_symbol("AAPL", date(2026, 7, 17), "PUT", 210.0)
    assert put.startswith("AAPL  ")
    assert "P" in put


def test_classify_iron_condor_multileg():
    o = _ready(
        strategy="Iron Condor",
        setup_id="options_credit_iron_condor",
        side="Neutral",
        strike_prices=[235.0, 242.5, 257.5, 265.0],
        symbol="TSLA",
    )
    assert classify_place_path(o) == "multi_leg_ready"


def test_classify_single_leg_debit_call():
    o = _ready(strategy="Long Call", setup_id="options_debit_call", side="long")
    assert classify_place_path(o) == "single_leg_debit"
    assert infer_call_put(o) == "CALL"


def test_classify_single_leg_put():
    o = _ready(strategy="Long Put", setup_id="options_debit_put", side="bear", strike_prices=[490.0])
    assert classify_place_path(o) == "single_leg_debit"
    assert infer_call_put(o) == "PUT"


def test_classify_credit_ready_only():
    o = _ready(
        strategy="Bull Put Credit Spread",
        setup_id="options_credit_bull_put",
        side="bull",
        strike_prices=[480.0, 475.0],
    )
    # multi-leg from 2 strikes
    assert classify_place_path(o) == "multi_leg_ready"
    single_credit = _ready(
        strategy="Cash Secured Put",
        setup_id="csp",
        side="short",
        strike_prices=[480.0],
    )
    assert classify_place_path(single_credit) in ("credit_ready", "unsupported")


def test_submit_order_dry_run_annotates_path():
    o = _ready()
    out = submit_order(o, live=False)
    assert out.status == "dry_run"
    assert out.broker_response.get("place_path") == "single_leg_debit"


def test_submit_order_live_multileg_ready_only(monkeypatch):
    calls: list[tuple[str, dict]] = []

    def fake_mcp(tool: str, payload: dict, **kwargs):
        calls.append((tool, payload))
        return {"status": "submitted"}

    monkeypatch.setattr("trading_agent.export.mac_execute.call_schwab_mcp", fake_mcp)
    o = _ready(
        strategy="Iron Condor",
        setup_id="options_credit_iron_condor",
        side="Neutral",
        strike_prices=[1.0, 2.0, 3.0, 4.0],
    )
    out = submit_order(o, live=True)
    assert out.status == "ready"
    assert out.broker_response.get("place_path") == "multi_leg_ready"
    assert calls == []  # never hits broker for multi-leg


def test_submit_order_live_single_leg_place_order(monkeypatch):
    calls: list[tuple[str, dict]] = []

    def fake_mcp(tool: str, payload: dict, **kwargs):
        calls.append((tool, payload))
        return {"status": "submitted", "dry_run": False, "symbol": payload.get("symbol")}

    monkeypatch.setattr("trading_agent.export.mac_execute.call_schwab_mcp", fake_mcp)
    o = _ready(strategy="Long Call", setup_id="options_debit_call", side="long")
    out = submit_order(o, live=True)
    assert out.status == "submitted"
    assert len(calls) == 1
    tool, payload = calls[0]
    assert tool == "place_order"
    assert payload["asset_type"] == "OPTION"
    assert payload["instruction"] == "BUY_TO_OPEN"
    assert payload["dry_run"] is False
    assert payload["confirm_live"] is True
    assert "C" in payload["symbol"]
    assert out.broker_response.get("occ_symbol")


def test_submit_order_live_equity_buy(monkeypatch):
    calls: list[tuple[str, dict]] = []

    def fake_mcp(tool: str, payload: dict, **kwargs):
        calls.append((tool, payload))
        return {"status": "submitted", "dry_run": False}

    monkeypatch.setattr("trading_agent.export.mac_execute.call_schwab_mcp", fake_mcp)
    o = _ready(
        instrument="underlying",
        strategy="ORB long",
        side="long",
        strike_prices=[],
        expiration="",
        quantity=10,
    )
    out = submit_order(o, live=True)
    assert out.status == "submitted"
    assert calls[0][0] == "place_order"
    assert calls[0][1]["asset_type"] == "EQUITY"
    assert calls[0][1]["instruction"] == "BUY"


def test_parse_expiration():
    assert parse_expiration_date("2026-08-15") == date(2026, 8, 15)
    assert parse_expiration_date("2026-08-15T00:00:00Z") == date(2026, 8, 15)
