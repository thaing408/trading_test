"""EP vs breakout setup_family classifier."""

from __future__ import annotations

from trading_agent.analysis.setup_family import (
    FAMILY_BREAKOUT,
    FAMILY_EP,
    apply_setup_family_to_entry,
    classify_setup_family,
)


def test_gap_continuation_is_ep():
    assert (
        classify_setup_family(method_tags=["multi_method", "gap_continuation_4d"])
        == FAMILY_EP
    )
    assert classify_setup_family(gap_continuation=True) == FAMILY_EP


def test_earnings_catalyst_is_ep():
    assert (
        classify_setup_family(catalyst="CRWD earnings beat", catalyst_type="earnings")
        == FAMILY_EP
    )
    assert classify_setup_family(notes="gap up on upgrade") == FAMILY_EP


def test_quiet_breakout():
    assert (
        classify_setup_family(
            method_tags=["multi_method", "swing_daily", "chart_patterns"],
            notes="structure break above resistance",
            thesis="clean range break",
        )
        == FAMILY_BREAKOUT
    )


def test_apply_tag_only_default(monkeypatch):
    monkeypatch.delenv("TRADING_AGENT_EP_SLOW", raising=False)
    row = {
        "symbol": "CRWD",
        "method_tags": ["gap_continuation_4d"],
        "max_risk_dollars": 200.0,
        "quantity": 2,
        "notes": "",
    }
    out = apply_setup_family_to_entry(row, apply_ep_slow=False)
    assert out["setup_family"] == FAMILY_EP
    assert out["max_risk_dollars"] == 200.0


def test_ep_slow_size_cut(monkeypatch):
    row = {
        "symbol": "CRWD",
        "method_tags": ["gap_continuation_4d"],
        "max_risk_dollars": 200.0,
        "quantity": 2,
        "notes": "",
    }
    out = apply_setup_family_to_entry(row, apply_ep_slow=True)
    assert out["setup_family"] == FAMILY_EP
    assert out["max_risk_dollars"] == 100.0
    assert out["quantity"] == 1
    assert out.get("ep_slow_applied") is True


def test_breakout_unaffected_by_ep_slow():
    row = {
        "symbol": "AAPL",
        "method_tags": ["swing_daily"],
        "max_risk_dollars": 200.0,
        "quantity": 2,
        "notes": "clean breakout",
    }
    out = apply_setup_family_to_entry(row, apply_ep_slow=True)
    assert out["setup_family"] == FAMILY_BREAKOUT
    assert out["max_risk_dollars"] == 200.0
