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
        broker_response={
            "occ_symbol": "TLT   260821P00080000",
            "status": "filled",
            "fill_price": 0.59,
        },
    )
    out = jn.notify_order_activity(
        order, live=True, fill_price=0.59, spot_price=81.76, fill_confirmed=True
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


def test_notify_order_submitted_posts_working_not_entry(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_AGENT_JOURNAL_ALERTS", "1")
    monkeypatch.setenv("TRADING_AGENT_JOURNAL_WORKING_ALERTS", "1")
    monkeypatch.setenv("TRADING_AGENT_JOURNAL_DEDUPE_FILE", str(tmp_path / "dedupe.json"))

    posts = []

    def fake_post(message, **kwargs):
        posts.append({"message": message, **kwargs})
        return {"ok": True}

    monkeypatch.setattr(jn, "post_journal_activity", fake_post)

    order = ReadyOrder(
        order_id="ord_working",
        symbol="AMD",
        action="ENTER",
        side="Bullish",
        instrument="options",
        strategy="multi",
        setup_id="multi_fvg",
        entry=100,
        stop=99,
        target=105,
        max_risk_dollars=50,
        status="submitted",
        broker_response={"status": "submitted", "occ_symbol": "AMD   260821C00100000"},
    )
    out = jn.notify_order_activity(order, live=True, fill_confirmed=False)
    assert out.get("ok") is True
    assert posts and "WORKING" in posts[0]["message"]
    assert "ENTRY" not in posts[0]["message"] or "WORKING" in posts[0]["message"]
    assert posts[0].get("mention") is False


def test_notify_skip_rth_and_cash(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_AGENT_JOURNAL_ALERTS", "1")
    monkeypatch.setenv("TRADING_AGENT_JOURNAL_SKIP_ALERTS", "1")
    monkeypatch.setenv("TRADING_AGENT_JOURNAL_DEDUPE_FILE", str(tmp_path / "dedupe.json"))
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
    monkeypatch.setenv("DISCORD_JOURNAL_CHANNEL_ID", "123")

    posts = []

    class _Resp:
        status = 200

        def read(self):
            return b'{"id":"1"}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=20):
        posts.append(json.loads(req.data.decode("utf-8")))
        return _Resp()

    monkeypatch.setattr(jn.urllib.request, "urlopen", fake_urlopen)

    order = ReadyOrder(
        order_id="ord_skip",
        symbol="CRWD",
        action="ENTER",
        side="Bullish",
        instrument="options",
        strategy="multi",
        setup_id="multi_swing",
        entry=200,
        stop=195,
        target=210,
        max_risk_dollars=100,
        status="skipped",
        skip_reason="before_rth_open",
        broker_response={"mode": "rth_gate", "message": "LIVE place blocked until 09:30 ET"},
    )
    out = jn.notify_skip_activity(order, live=True)
    assert out.get("ok") is True
    assert "SKIPPED" in posts[0]["content"]
    assert "CRWD" in posts[0]["content"]
    assert "09:30" in posts[0]["content"]

    # Day dedupe
    out2 = jn.notify_skip_activity(order, live=True)
    assert out2.get("skipped") and out2.get("reason") == "duplicate"
    assert len(posts) == 1

    cash = ReadyOrder(
        order_id="ord_cash",
        symbol="ZS",
        action="ENTER",
        side="Bullish",
        instrument="options",
        strategy="multi",
        setup_id="multi_swing",
        entry=150,
        stop=145,
        target=160,
        max_risk_dollars=100,
        status="skipped",
        skip_reason="max_open_risk",
    )
    out3 = jn.notify_skip_activity(cash, live=True)
    assert out3.get("ok") is True
    assert "max open risk" in posts[-1]["content"].lower()

def test_skip_reason_should_alert_prefixes():
    assert jn.skip_reason_should_alert("before_rth_open")
    assert jn.skip_reason_should_alert("insufficient_cash:need=100:have=50")
    assert jn.skip_reason_should_alert("insufficient_margin:need=200:have=10")
    assert not jn.skip_reason_should_alert("already_processed")
    assert not jn.skip_reason_should_alert("")

def test_post_disabled(monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_JOURNAL_ALERTS", "0")
    out = jn.post_journal_activity("hello")
    assert out.get("skipped")


def test_notify_exit_matches_qqq_layout(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_AGENT_JOURNAL_ALERTS", "1")
    monkeypatch.setenv("TRADING_AGENT_JOURNAL_DEDUPE_FILE", str(tmp_path / "dedupe.json"))
    monkeypatch.setenv("TRADING_AGENT_OPTION_PROFIT_PCT", "25")

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

    class Lot:
        symbol = "QQQ"
        occ_symbol = "QQQ   260812C00725000"
        quantity = 1
        lot_id = "lot1"
        setup_id = "bull_breakout"
        strategy = "scalp"
        fill_entry = 0.61
        entry = 723.77
        exit_price = 0.82
        broker_meta = {"option_entry_premium": 0.61}
        exit_reason = "option_target_38pct"

    out = jn.notify_exit_activity(
        Lot(),
        reason="option_target_37pct",
        live=True,
        option_mark=0.82,
        option_entry=0.61,
        spot_price=724.79,
        order_id="1007567425260",
    )
    assert out.get("ok") is True
    payload = json.loads(captured["cmd"][2])
    assert payload["label"] == "MULTI AUTO"
    assert payload["event"] == "exit"
    assert payload["setup"] == "bull_breakout"
    assert payload["qqq_price"] == 724.79
    assert payload["fill_price"] == 0.82
    assert payload["pnl"] == 21.0  # (0.82-0.61)*100
    assert payload["order_id"] == "1007567425260"
    assert "HARD TARGET" in payload["reason"]
    assert "entry $0.61 → $0.82" in payload["reason"]
    assert "entry_price" not in payload or payload.get("entry_price") is None


def test_format_exit_reason_hard_target():
    text = jn._format_exit_reason(
        raw_reason="option_target_38pct",
        entry_opt=0.61,
        exit_opt=0.84,
        profit_pct_limit=25,
    )
    assert text.startswith("HARD TARGET")
    assert "entry $0.61 → $0.84" in text
    assert "limit +25%" in text
