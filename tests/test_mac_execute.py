"""Tests for macOS auto-trade book → ready orders (fail-closed)."""

from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from trading_agent.export.mac_execute import (
    build_ready_orders,
    entry_fingerprint,
    format_checklist,
    in_consumer_window,
    in_qt_window,
    validate_enter,
)


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
