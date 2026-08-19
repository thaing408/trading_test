"""Discord consumer cycle: skip flood vs one digest with skip_reason."""

from __future__ import annotations

from types import SimpleNamespace

from trading_agent.discord import paper_activity as pa


def _order(**kwargs):
    defaults = dict(
        status="skipped",
        symbol="JPM",
        action="ENTER",
        side="Bullish",
        skip_reason="already_processed",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_partition_cycle_orders_splits_skips():
    orders = [
        _order(status="skipped", symbol="JPM"),
        _order(status="submitted", symbol="NVDA", skip_reason=""),
        _order(status="failed", symbol="AAPL", skip_reason=""),
    ]
    actionable, skipped = pa.partition_cycle_orders(orders)
    assert [o.symbol for o in actionable] == ["NVDA", "AAPL"]
    assert [o.symbol for o in skipped] == ["JPM"]


def test_format_orders_batch_includes_skip_reason():
    text = pa.format_orders_batch([_order()])
    assert "JPM" in text
    assert "already_processed" in text


def test_format_skip_summary_groups_reasons():
    skipped = [
        _order(symbol="JPM", skip_reason="already_processed"),
        _order(symbol="NVDA", skip_reason="already_processed"),
        _order(symbol="META", skip_reason="after_entry_window", side="Bearish"),
    ]
    text = pa.format_skip_summary(skipped)
    assert "already_processed" in text
    assert "after_entry_window" in text
    assert "JPM" in text
    assert "META" in text
    assert "not sent to broker" in text


def test_should_post_skip_summary_once_per_fingerprint(tmp_path, monkeypatch):
    monkeypatch.setattr(pa, "_SKIP_DIGEST_LAST", "")
    monkeypatch.setenv("TRADING_AGENT_STATE_DIR", str(tmp_path))
    skipped = [_order(symbol="JPM"), _order(symbol="NVDA")]
    assert pa.should_post_skip_summary(skipped) is True
    assert pa.should_post_skip_summary(skipped) is False
    # Reason change → post again
    changed = [_order(symbol="JPM", skip_reason="after_entry_window")]
    assert pa.should_post_skip_summary(changed) is True


def test_interesting_manage_drops_holds():
    rows = [
        {"action": "hold", "symbol": "QQQ"},
        {"action": "exit", "symbol": "NVDA"},
        {"action": "flatten_all"},
    ]
    out = pa.interesting_manage_rows(rows)
    assert [r["action"] for r in out] == ["exit", "flatten_all"]


def test_post_orders_batch_silent_when_empty(monkeypatch):
    called = []
    monkeypatch.setattr(pa, "post_activity", lambda *a, **k: called.append((a, k)) or [])
    assert pa.post_orders_batch([]) == []
    assert called == []
