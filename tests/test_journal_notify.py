"""Journal Discord notify helpers (no network)."""

from __future__ import annotations

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


def test_notify_order_builds_and_posts(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_AGENT_JOURNAL_ALERTS", "1")
    monkeypatch.setenv("TRADING_AGENT_JOURNAL_DEDUPE_FILE", str(tmp_path / "dedupe.json"))
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("DISCORD_JOURNAL_CHANNEL_ID", "1514644765797515426")
    monkeypatch.setenv("DISCORD_JOURNAL_MENTION_USER_ID", "493638750086365194")

    captured = {}

    class _Resp:
        status = 200

        def read(self):
            return b'{"id":"1"}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=20):
        captured["url"] = req.full_url
        captured["data"] = req.data
        captured["headers"] = dict(req.header_items()) if hasattr(req, "header_items") else {}
        # Request stores headers differently
        captured["body"] = req.data.decode() if isinstance(req.data, bytes) else req.data
        return _Resp()

    monkeypatch.setattr(jn.urllib.request, "urlopen", fake_urlopen)

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
    out = jn.notify_order_activity(order, live=True)
    assert out.get("ok") is True
    body = captured["body"]
    assert "493638750086365194" in body
    assert "TLT" in body
    assert "ENTRY SUBMITTED" in body
    # second call deduped
    out2 = jn.notify_order_activity(order, live=True)
    assert out2.get("skipped") and out2.get("reason") == "duplicate"


def test_post_disabled(monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_JOURNAL_ALERTS", "0")
    out = jn.post_journal_activity("hello")
    assert out.get("skipped")
