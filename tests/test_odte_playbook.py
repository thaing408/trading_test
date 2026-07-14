"""Tests for QQQ/SPY 0DTE Shen-style playbook helpers."""

from trading_agent.odte.playbook import (
    OdtePlaybookConfig,
    format_odte_brief,
    is_structural_level_name,
    level_allowed_for_entry,
    rejection_close_ok,
    rsi_series,
    signal_side_for_touch,
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


def test_signal_side_for_touch_respects_rsi_gates():
    cfg = OdtePlaybookConfig(put_rsi=74, call_rsi=26)
    assert signal_side_for_touch("resistance", 80, cfg) == "PUT"
    assert signal_side_for_touch("resistance", 60, cfg) is None
    assert signal_side_for_touch("support", 20, cfg) == "CALL"
    assert signal_side_for_touch("support", 40, cfg) is None


def test_level_allowed_structural_flag_blocks_whole_dollar():
    cfg = OdtePlaybookConfig(use_whole_dollar_levels=False)
    assert level_allowed_for_entry("ORH", cfg)
    assert level_allowed_for_entry("PDL", cfg)
    assert not level_allowed_for_entry("whole $715", cfg)
    assert is_structural_level_name("PMH")
    assert not is_structural_level_name("whole $720")
    cfg_on = OdtePlaybookConfig(use_whole_dollar_levels=True)
    assert level_allowed_for_entry("whole $715", cfg_on)
    # shipped default after TOS A/B keeps whole-$ rails
    assert OdtePlaybookConfig().use_whole_dollar_levels is True


def test_rejection_close_ok():
    assert rejection_close_ok("resistance", 100.0, 101.0, require=True)  # close below resistance
    assert not rejection_close_ok("resistance", 102.0, 101.0, require=True)
    assert rejection_close_ok("support", 101.0, 100.0, require=True)
    assert not rejection_close_ok("support", 99.0, 100.0, require=True)
    assert rejection_close_ok("resistance", 102.0, 101.0, require=False)
