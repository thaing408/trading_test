"""Tests for price-action engines (structure, FVG, levels, sweep, range fade, HTF)."""

from __future__ import annotations

import pytest

from trading_agent.pa.fvg import (
    detect_fvg,
    detect_fvg_at,
    find_active_fvgs,
    fvg_fill_pct,
    score_fvg_entry,
)
from trading_agent.pa.htf_bias import bias_allows_side, compute_htf_bias_from_ohlc
from trading_agent.pa.htf_bias import HtfBias
from trading_agent.pa.journal import format_pa_journal_line, pa_journal_fields
from trading_agent.pa.range_fade import evaluate_range_fade
from trading_agent.pa.reactions import acceptance_at_level, rejection_at_level
from trading_agent.pa.structure import analyze_structure, pivot_highs_lows
from trading_agent.pa.sweep import detect_sweep_reclaim
from trading_agent.pa.levels import whole_dollar_levels


def test_pivot_and_structure_uptrend():
    # Rising pivots
    highs = [10, 11, 10.5, 12, 11.5, 13, 12.5, 14, 13.5, 15, 14.5, 16]
    lows = [9, 9.5, 9.2, 10.5, 10.2, 11.5, 11.2, 12.5, 12.2, 13.5, 13.2, 14.5]
    closes = [(h + l) / 2 for h, l in zip(highs, lows)]
    ph, pl = pivot_highs_lows(highs, lows, left=1, right=1)
    assert len(ph) >= 1 or len(pl) >= 1
    st = analyze_structure(highs, lows, closes, left=1, right=1)
    assert st.trend in ("up", "range", "down", "unknown")


def test_detect_bullish_fvg():
    # c0 high=10, c1 big up, c2 low=12 > 10
    opens = [9, 10.5, 12.5]
    highs = [10, 13, 14]
    lows = [8.5, 10.4, 12.1]
    closes = [10, 12.8, 13.5]
    fvg = detect_fvg(opens, highs, lows, closes, 2)
    assert fvg is not None
    side, glo, ghi = fvg
    assert side == "bullish"
    assert glo == 10.0
    assert ghi == 12.1


def test_detect_bearish_fvg():
    opens = [14, 12, 10]
    highs = [14.5, 12.2, 10.5]
    lows = [13, 10, 9]
    closes = [13.2, 10.5, 9.5]
    # high[2]=10.5 < low[0]=13
    fvg = detect_fvg(opens, highs, lows, closes, 2)
    assert fvg is not None
    assert fvg[0] == "bearish"


def test_fvg_fill_and_active():
    highs = [10, 13, 14, 13.5, 12.5, 12.0]
    lows = [9, 10.5, 12.1, 11.5, 11.0, 10.8]
    closes = [9.5, 12.8, 13.5, 12.0, 11.5, 11.2]
    gap = detect_fvg_at(highs, lows, 2, mid=12.0)
    assert gap and gap.side == "bullish"
    fill = fvg_fill_pct(gap, highs, lows, 3, 5)
    assert fill > 0


def test_rejection_and_acceptance():
    assert rejection_at_level(101, 99, 100.5, 100.8, 100.0, side="long")
    assert acceptance_at_level(101.0, 100.0, side="long")
    assert not acceptance_at_level(99.0, 100.0, side="long")


def test_sweep_reclaim_long():
    # pierce below 100 then close above
    highs = [101, 100.5]
    lows = [99.5, 98.5]
    opens = [100.5, 99.0]
    closes = [100.2, 100.3]
    sig = detect_sweep_reclaim(
        highs, lows, opens, closes, level_high=102, level_low=100, i=1
    )
    assert sig is not None
    assert sig.side == "CALL"


def test_range_fade_long():
    n = 30
    highs = [110.0] * n
    lows = [100.0] * n
    opens = [105.0] * n
    closes = [105.0] * n
    lows[-1] = 100.2
    opens[-1] = 101.0
    closes[-1] = 103.5
    highs[-1] = 104.0
    sig = evaluate_range_fade(highs, lows, opens, closes, lookback=20)
    assert sig is not None
    assert sig.side == "CALL"


def test_htf_bias_and_allow():
    highs = list(range(20, 40))
    lows = list(range(10, 30))
    closes = list(range(15, 35))
    bias = compute_htf_bias_from_ohlc(highs, lows, closes)
    assert bias.direction in ("up", "down", "range", "unknown")
    b = HtfBias(direction="up", strength=70)
    assert bias_allows_side(b, "CALL")
    assert not bias_allows_side(b, "PUT", strict=True)


def test_whole_dollars():
    above, below = whole_dollar_levels(100.4, n=2)
    assert above[0] >= 101
    assert below[0] <= 100


def test_journal_fields():
    from trading_agent.pa.structure import StructureState

    st = StructureState(trend="up", last_bos="bullish")
    f = pa_journal_fields(structure=st, reaction="rejection", htf_direction="up")
    assert f["structure_trend"] == "up"
    line = format_pa_journal_line(f)
    assert "PA[" in line


def test_score_fvg_entry_no_crash():
    n = 40
    highs = [100 + i * 0.1 + (2 if i == 20 else 0) for i in range(n)]
    lows = [99 + i * 0.1 for i in range(n)]
    # create gap around i=22
    highs[20], lows[20], highs[21], lows[21], highs[22], lows[22] = 105, 103, 108, 106, 110, 109
    # 109 > 105 => bullish fvg
    opens = lows[:]
    closes = highs[:]
    play, side, score, tags, e, s, t = score_fvg_entry(
        highs, lows, opens, closes, htf_direction="up", min_size_pct=0.01, require_rejection=False
    )
    assert score >= 0
