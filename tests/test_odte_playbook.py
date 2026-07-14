"""Tests for QQQ/SPY 0DTE Shen-style playbook helpers."""

from trading_agent.odte.playbook import (
    OdtePlaybookConfig,
    format_odte_brief,
    rsi_series,
    whole_dollar_levels,
)


def test_rsi_series_length_and_range():
    closes = [100 + i * 0.1 for i in range(40)]
    r = rsi_series(closes, 14)
    assert len(r) == len(closes)
    assert all(0 <= x <= 100 for x in r)


def test_whole_dollar_levels_around_price():
    above, below = whole_dollar_levels(711.72, n=3)
    assert above[0] >= 712
    assert below[0] <= 712
    assert all(x == int(x) for x in above + below)


def test_format_brief_structure_with_empty_setups():
    from trading_agent.odte.playbook import KeyLevels, OdteSessionBrief

    brief = OdteSessionBrief(
        symbol="QQQ",
        asof="2026-07-13T12:00:00-04:00",
        in_window=False,
        window_note="OUTSIDE window",
        levels=KeyLevels(
            last=711.72,
            whole_above=[712.0, 713.0],
            whole_below=[711.0, 710.0],
            pdh=718.0,
            pdl=710.0,
            pmh=715.0,
            pml=712.0,
            or_high=714.0,
            or_low=711.0,
        ),
        rsi_1m=48.0,
        setups=[],
        risk_note="max $250",
        source="test",
    )
    text = format_odte_brief(brief)
    assert "QQQ 0DTE" in text
    assert "PDH" in text and "718" in text
    assert "RSI" in text
    assert "No entry now" in text or "No entry" in text
