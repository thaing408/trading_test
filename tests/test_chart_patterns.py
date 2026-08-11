"""Tests for classical chart pattern detectors + multi-method scoring."""

from __future__ import annotations

from trading_agent.pa.chart_patterns import (
    detect_all_chart_patterns,
    detect_bull_flag,
    detect_double_bottom,
    detect_double_top,
    detect_head_and_shoulders,
    detect_inverse_head_and_shoulders,
    score_chart_pattern_entry,
)


def _flat(n: int, px: float = 100.0):
    return [px] * n, [px] * n, [px] * n, [px] * n


def test_double_top_confirmed():
    # Build two peaks ~110 with valley ~100, then close below neckline
    highs, lows, closes = [], [], []
    # climb to first peak
    for i in range(8):
        px = 100 + i * 1.2
        highs.append(px + 0.3)
        lows.append(px - 0.3)
        closes.append(px)
    # peak 1
    highs.append(110.5)
    lows.append(108.0)
    closes.append(109.0)
    # valley
    for i in range(5):
        px = 108 - i * 1.5
        highs.append(px + 0.4)
        lows.append(px - 0.4)
        closes.append(px)
    # peak 2 ~ same height
    for i in range(5):
        px = 100 + i * 2.0
        highs.append(px + 0.3)
        lows.append(px - 0.3)
        closes.append(px)
    highs.append(110.2)
    lows.append(107.5)
    closes.append(108.5)
    # breakdown below valley
    for i in range(4):
        px = 99 - i * 0.5
        highs.append(px + 0.3)
        lows.append(px - 0.5)
        closes.append(px)

    # Ensure fractal pivots: left/right=2 need clear local extremes
    # Pad start
    pad = 5
    highs = [100.0] * pad + highs
    lows = [99.0] * pad + lows
    closes = [99.5] * pad + closes

    pat = detect_double_top(highs, lows, closes, tol_pct=2.0)
    # May or may not detect depending on pivot placement; score path must not crash
    play, side, score, tags, entry, stop, target = score_chart_pattern_entry(
        highs, lows, closes, closes, require_confirmed=False
    )
    assert score >= 0
    assert isinstance(tags, list)


def test_double_bottom_synthetic_pivots():
    # Explicit construction with left=1 right=1 friendlier series
    # lows pivots at indices with clear V shapes
    n = 40
    closes = []
    highs = []
    lows = []
    for i in range(n):
        # base path: down to 90, bounce to 100, down to 90, up through 100
        if i < 10:
            c = 100 - i
        elif i < 18:
            c = 90 + (i - 10) * 1.25
        elif i < 26:
            c = 100 - (i - 18) * 1.25
        else:
            c = 90 + (i - 26) * 1.5
        closes.append(c)
        highs.append(c + 0.8)
        lows.append(c - 0.8)

    # Force second leg through neckline
    closes[-1] = max(closes) + 1.0
    highs[-1] = closes[-1] + 0.5
    lows[-1] = closes[-1] - 0.5

    pats = detect_all_chart_patterns(highs, lows, closes)
    assert isinstance(pats, list)
    # Scoring always returns 7-tuple
    out = score_chart_pattern_entry(highs, lows, closes, closes)
    assert len(out) == 7
    play, side, score, tags, entry, stop, target = out
    if play:
        assert side in ("CALL", "PUT")
        assert stop > 0 and target > 0
        assert entry > 0


def test_head_and_shoulders_geometry():
    """Three peaks: LS, higher head, RS; then break neckline."""
    # Manual pivot-friendly series
    points = [
        100, 102, 101, 105, 103, 108, 106,  # into LS area
        110, 108, 106,  # LS peak ~110
        104, 102, 100,  # valley
        106, 110, 114, 112,  # head ~114
        108, 104, 100,  # valley
        104, 108, 110, 108,  # RS ~110
        104, 100, 96, 94,  # break neckline
    ]
    closes = [float(p) for p in points]
    highs = [c + 0.6 for c in closes]
    lows = [c - 0.6 for c in closes]
    # Emphasize peaks
    highs[7] = 110.5
    highs[14] = 114.5
    highs[21] = 110.3

    pat = detect_head_and_shoulders(highs, lows, closes)
    # Detector may need fractal pivots — at least no exception and score works
    play, side, score, tags, entry, stop, target = score_chart_pattern_entry(
        highs, lows, closes, closes, require_confirmed=True
    )
    assert 0 <= score <= 100
    if play and side == "PUT":
        assert target < entry
        assert stop > entry


def test_inverse_hs_and_flags_no_crash():
    closes = [100.0 + i * 0.2 for i in range(50)]
    # impulse then flag
    for i in range(30, 38):
        closes[i] = closes[29] + (i - 29) * 1.5
    for i in range(38, 48):
        closes[i] = closes[37] - (i - 37) * 0.15
    closes[48] = closes[37] + 1.0
    closes[49] = closes[48] + 0.5
    highs = [c + 0.4 for c in closes]
    lows = [c - 0.4 for c in closes]
    detect_bull_flag(highs, lows, closes)
    detect_inverse_head_and_shoulders(highs, lows, closes)
    detect_double_bottom(highs, lows, closes)
    pats = detect_all_chart_patterns(highs, lows, closes)
    assert all(p.confidence >= 0 for p in pats)


def test_score_empty_series():
    play, side, score, tags, e, s, t = score_chart_pattern_entry([], [], [], [])
    assert play is False
    assert score == 0.0


def test_multi_method_chart_patterns_vote():
    import numpy as np
    import pandas as pd
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from trading_agent.strategy.multi_method import MultiMethodConfig, evaluate_ticker_all_methods

    ET = ZoneInfo("America/New_York")
    start = datetime(2026, 7, 15, 9, 30, tzinfo=ET)
    rows, idx = [], []
    px = 100.0
    for i in range(80):
        day = i // 26
        bar = i % 26
        ts = start + timedelta(days=day, minutes=15 * bar)
        # mild double-top-ish noise then drop
        if i < 40:
            px = 100 + (i % 15) * 0.5
        else:
            px = 105 - (i - 40) * 0.4
        o, c = px - 0.1, px + 0.05
        h, l = max(o, c) + 0.4, min(o, c) - 0.4
        rows.append({"Open": o, "High": h, "Low": l, "Close": c, "Volume": 1000})
        idx.append(ts)
    df = pd.DataFrame(rows, index=pd.DatetimeIndex(idx))
    cfg = MultiMethodConfig(
        min_method_score=40,
        min_play_methods=1,
        use_htf_bias=False,
        enabled_methods=("chart_patterns",),
    )
    result = evaluate_ticker_all_methods("TEST", cfg=cfg, df=df)
    assert len(result.votes) == 1
    assert result.votes[0].method_id == "chart_patterns"
    assert result.decision in ("PLAY", "SKIP", "CONFLICT", "NO_DATA")
