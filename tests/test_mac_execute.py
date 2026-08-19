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
    in_live_entry_window,
    in_qt_window,
    live_entry_blocked_reason,
    infer_call_put,
    is_terminal_broker_reject,
    option_contract_precheck,
    parse_expiration_date,
    resolve_listed_option_strike,
    strike_grid_candidates,
    submit_order,
    validate_enter,
)
from datetime import date
from trading_agent.export.multi_method_book import _option_strike


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
    # Prep window starts 9:25 — still before RTH live gate
    prep = datetime(2026, 7, 16, 9, 25, tzinfo=ET)
    assert in_consumer_window(prep)


def test_live_entry_window_blocks_preopen():
    """LIVE MARKET place only at/after 09:30 ET (not 09:25 prep)."""
    ET = ZoneInfo("America/New_York")
    pre = datetime(2026, 8, 19, 9, 25, tzinfo=ET)  # Wed
    open_ts = datetime(2026, 8, 19, 9, 30, tzinfo=ET)
    mid = datetime(2026, 8, 19, 10, 15, tzinfo=ET)
    after = datetime(2026, 8, 19, 11, 1, tzinfo=ET)
    weekend = datetime(2026, 8, 15, 10, 0, tzinfo=ET)

    assert in_consumer_window(pre)
    assert not in_live_entry_window(pre)
    assert live_entry_blocked_reason(pre) == "before_rth_open"

    assert in_live_entry_window(open_ts)
    assert live_entry_blocked_reason(open_ts) == ""
    assert in_live_entry_window(mid)
    assert live_entry_blocked_reason(mid) == ""

    assert not in_live_entry_window(after)
    assert live_entry_blocked_reason(after) == "after_entry_window"
    assert not in_live_entry_window(weekend)
    assert live_entry_blocked_reason(weekend) == "before_rth_open"


def test_preopen_live_escape_hatch(monkeypatch):
    ET = ZoneInfo("America/New_York")
    pre = datetime(2026, 8, 19, 9, 25, tzinfo=ET)
    monkeypatch.setenv("TRADING_AGENT_AUTO_TRADE_ALLOW_PREOPEN_LIVE", "1")
    assert live_entry_blocked_reason(pre) == ""
    assert not in_live_entry_window(pre)  # window helper stays truthful


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
        expiration="2026-08-28",  # keep ≥3 DTE vs calendar "today" in dual-DTE precheck
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


def test_option_strike_uses_listed_increments():
    # Avoid inventing V 357 / GE 372 / ZS 183 style strikes
    assert _option_strike(184.35, "PUT") == 180.0  # $2.5 grid under $200
    assert _option_strike(358.91, "PUT") == 350.0  # $5 grid at $200+
    assert _option_strike(369.22, "CALL") == 375.0  # $5 OTM call grid


def test_strike_grid_includes_common_listed():
    cands = strike_grid_candidates(183.0, spot=184.0)
    assert 180.0 in cands
    assert 182.5 in cands
    assert 185.0 in cands


def test_resolve_listed_option_strike_snaps_via_quotes():
    preferred = 183.0
    exp = date(2026, 8, 21)

    def fake_mcp(tool: str, payload: dict, **kwargs):
        assert tool == "get_quotes"
        quotes = []
        for sym in payload["symbols"]:
            # Only 182.50 and 185 exist
            if "00182500" in sym or "00185000" in sym:
                quotes.append(
                    {"symbol": sym, "asset_type": "OPTION", "bid": 1.0, "ask": 1.2}
                )
            else:
                quotes.append({"symbol": sym, "error": "Symbol not found"})
        return {"quotes": quotes}

    strike, occ, meta = resolve_listed_option_strike(
        "ZS", exp, "PUT", preferred, spot=184.0, call_mcp=fake_mcp
    )
    assert strike == 182.5
    assert occ == format_occ_symbol("ZS", exp, "PUT", 182.5)
    assert meta.get("strike_snapped_from") == 183.0


def test_precheck_resolve_listed_skips_when_none_quote():
    o = _ready(
        symbol="ZS",
        strategy="Multi-method long put (chart_patterns)",
        side="Bearish",
        strike_prices=[183.0],
        entry=184.0,
    )

    def fake_mcp(tool: str, payload: dict, **kwargs):
        return {
            "quotes": [
                {"symbol": s, "error": "Symbol not found"} for s in payload["symbols"]
            ]
        }

    ok, reason, meta = option_contract_precheck(
        o, resolve_listed=True, call_mcp=fake_mcp
    )
    assert ok is False
    assert reason == "occ_not_listed"


def test_is_terminal_broker_reject_400():
    assert is_terminal_broker_reject(
        {
            "error": True,
            "error_type": "HTTPStatusError",
            "message": "Client error '400 Bad Request' for url 'https://api.schwabapi.com/.../orders'",
        }
    )
    assert not is_terminal_broker_reject({"status": "submitted"})


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
        if tool == "get_quotes":
            # Pretend preferred OCC (and neighbors) are listed
            return {
                "quotes": [
                    {
                        "symbol": s,
                        "asset_type": "OPTION",
                        "bid": 1.0,
                        "ask": 1.2,
                    }
                    for s in payload.get("symbols") or []
                ]
            }
        return {"status": "submitted", "dry_run": False, "symbol": payload.get("symbol")}

    monkeypatch.setattr("trading_agent.export.mac_execute.call_schwab_mcp", fake_mcp)
    o = _ready(strategy="Long Call", setup_id="options_debit_call", side="long")
    out = submit_order(o, live=True)
    assert out.status == "submitted"
    place_calls = [c for c in calls if c[0] == "place_order"]
    assert len(place_calls) == 1
    tool, payload = place_calls[0]
    assert tool == "place_order"
    assert payload["asset_type"] == "OPTION"
    assert payload["instruction"] == "BUY_TO_OPEN"
    assert payload["dry_run"] is False
    assert payload["confirm_live"] is True
    assert "C" in payload["symbol"]
    assert out.broker_response.get("occ_symbol")
    assert any(c[0] == "get_quotes" for c in calls)


def test_submit_order_live_equity_buy(monkeypatch):
    calls: list[tuple[str, dict]] = []

    def fake_mcp(tool: str, payload: dict, **kwargs):
        calls.append((tool, payload))
        return {"status": "submitted", "dry_run": False}

    monkeypatch.setattr("trading_agent.export.mac_execute.call_schwab_mcp", fake_mcp)
    monkeypatch.setenv("TRADING_AGENT_OPTIONS_ONLY", "0")
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
