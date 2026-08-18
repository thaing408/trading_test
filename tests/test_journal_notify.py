"""Journal Discord notify helpers (no network)."""

from __future__ import annotations

import json

from trading_agent.export.mac_execute import ReadyOrder
from trading_agent.ops import journal_notify as jn


def test_notify_order_activity_skips_non_live():
    order = ReadyOrder(
        order_id="x1",
        symbol="AMD",
        action="ENTER",
        side="Bullish",
        instrument="options",
        strategy="test",
        setup_id="t",
        entry=1,
        stop=0.5,
        target=2,
        max_risk_dollars=50,
        status="submitted",
    )
    out = jn.notify_order_activity(order, live=False)
    assert out.get("skipped")


def test_notify_order_uses_trade_event_script(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_AGENT_JOURNAL_ALERTS", "1")
    monkeypatch.setenv("TRADING_AGENT_JOURNAL_DEDUPE_FILE", str(tmp_path / "dedupe.json"))

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        class P:
            returncode = 0
            stdout = "Posted via bot: HTTP 200"
            stderr = ""
        return P()

    monkeypatch.setattr(jn.subprocess, "run", fake_run)
    monkeypatch.setattr(jn, "JOURNAL_SCRIPT", tmp_path / "post-trade-event.sh")
    (tmp_path / "post-trade-event.sh").write_text("#!/bin/bash\n")

    order = ReadyOrder(
        order_id="ord99",
        symbol="TLT",
        action="ENTER",
        side="Bearish",
        instrument="options",
        strategy="Multi-method long put (fvg)",
        setup_id="multi_fvg",
        entry=81,
        stop=82,
        target=80,
        max_risk_dollars=50,
        quantity=1,
        expiration="2026-08-21",
        strike_prices=[80.0],
        status="submitted",
        broker_response={"occ_symbol": "TLT   260821P00080000"},
    )
    out = jn.notify_order_activity(
        order, live=True, fill_price=0.59, spot_price=81.76
    )
    assert out.get("ok") is True
    assert "post-trade-event.sh" in str(captured["cmd"][0])
    assert "--json" in captured["cmd"]
    payload = json.loads(captured["cmd"][2])
    assert payload["event"] == "entry"
    assert payload["label"] == "MULTI AUTO"
    assert payload["underlying"] == "TLT"
    assert payload["setup"] == "multi_fvg"
    assert payload["fill_price"] == 0.59
    assert payload["qqq_price"] == 81.76
    assert "TLT" in payload["symbol"]
    assert payload["description"].startswith("TLT")


def test_post_disabled(monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_JOURNAL_ALERTS", "0")
    out = jn.post_journal_activity("hello")
    assert out.get("skipped")
