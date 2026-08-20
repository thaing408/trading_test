"""Tests for daily swing scanner."""

from __future__ import annotations

from trading_agent.strategy.swing_scan import (
    SwingScanConfig,
    clamp_stop_to_atr,
    format_swing_scan_report,
    score_swing_from_ohlc,
)


def _uptrend_series(n: int = 120):
    closes = []
    highs = []
    lows = []
    opens = []
    px = 100.0
    for i in range(n):
        px = px + 0.35 + (0.15 if i % 7 == 0 else 0.0)
        # mild pullbacks every 10 bars
        if i % 10 == 9:
            px -= 1.2
        o = px - 0.2
        c = px + 0.15
        h = max(o, c) + 0.5
        l = min(o, c) - 0.4
        opens.append(o)
        highs.append(h)
        lows.append(l)
        closes.append(c)
    return opens, highs, lows, closes


def test_score_uptrend_structure_long():
    o, h, l, c = _uptrend_series()
    # RS benchmark slightly weaker
    rs = [x * 0.99 for x in c]
    cfg = SwingScanConfig(
        min_score=50.0,
        allow_structure_only=True,
        require_confirmed_pattern=False,
        min_atr_pct=0.5,
        max_atr_pct=15.0,
        use_rs=True,
    )
    cand = score_swing_from_ohlc(h, l, o, c, cfg=cfg, rs_closes=rs, symbol="TEST")
    assert cand.score > 0
    assert cand.trend in ("up", "range", "down", "unknown")
    # Strong synthetic uptrend should often produce CALL
    if cand.play:
        assert cand.side == "CALL"
        assert cand.stop < cand.entry
        assert cand.target > cand.entry


def test_score_insufficient_bars():
    cand = score_swing_from_ohlc(
        [1, 2, 3], [0.5, 1, 2], [1, 2, 2.5], [1, 2, 2.8], symbol="X"
    )
    assert cand.play is False
    assert "insufficient" in (cand.reasons[0] if cand.reasons else "")


def test_format_report_empty_play():
    from trading_agent.strategy.swing_scan import SwingCandidate

    c = SwingCandidate(
        symbol="ZZZ",
        play=False,
        side="",
        score=40.0,
        style="none",
        tags=["x"],
        reasons=["weak"],
    )
    text = format_swing_scan_report([c])
    assert "Daily swing scan" in text
    assert "No PLAY" in text or "PLAY" in text


def test_clamp_stop_to_atr_crwd_zs_scale():
    """CRWD-like: entry 213 stop 119 (~44%) → pull to 1.5×ATR."""
    entry, fat_stop, atr = 212.92, 118.61, 212.92 * 0.041
    new_stop, clamped = clamp_stop_to_atr(entry, fat_stop, "CALL", atr, max_atr_mult=1.5)
    assert clamped is True
    assert new_stop == entry - 1.5 * atr
    assert (entry - new_stop) / entry < 0.08  # ~6.2% vs 44%

    # ZS-like ~26% → still capped
    entry2, fat2, atr2 = 185.70, 137.75, 185.70 * 0.042
    new2, c2 = clamp_stop_to_atr(entry2, fat2, "CALL", atr2, max_atr_mult=1.5)
    assert c2 is True
    assert abs(new2 - (entry2 - 1.5 * atr2)) < 1e-6

    # Already tight → unchanged
    tight = entry - 1.0 * atr
    same, c3 = clamp_stop_to_atr(entry, tight, "CALL", atr, max_atr_mult=1.5)
    assert c3 is False
    assert same == tight


def test_score_swing_caps_fat_pattern_stop():
    """Synthetic double-bottom with ancient low → stop must be ATR-capped."""
    o, h, l, c = _uptrend_series(150)
    # Inject a very old deep low so pattern stop would be absurd if used raw
    l[20] = min(c) * 0.55
    cfg = SwingScanConfig(
        min_score=40.0,
        allow_structure_only=True,
        require_confirmed_pattern=False,
        min_atr_pct=0.3,
        max_atr_pct=20.0,
        max_stop_atr_mult=1.5,
        use_rs=False,
    )
    cand = score_swing_from_ohlc(h, l, o, c, cfg=cfg, symbol="FAT")
    if cand.play and cand.side == "CALL" and cand.entry > 0 and cand.stop > 0:
        atr_abs = cand.entry * (cand.atr_pct / 100.0) if cand.atr_pct else cand.entry * 0.02
        assert (cand.entry - cand.stop) <= 1.5 * atr_abs * 1.05 + 1e-6


def test_require_pattern_blocks_structure_only():
    o, h, l, c = _uptrend_series()
    cfg = SwingScanConfig(
        min_score=40.0,
        allow_structure_only=False,
        require_confirmed_pattern=True,
        min_atr_pct=0.3,
        max_atr_pct=20.0,
    )
    cand = score_swing_from_ohlc(h, l, o, c, cfg=cfg, symbol="T")
    # Without a confirmed pattern, should not PLAY
    if cand.style == "structure":
        assert cand.play is False or cand.pattern_name
    if not cand.pattern_name or cand.style == "none":
        # structure-only path disabled
        assert cand.play is False or cand.style in ("pattern", "both")


def test_multi_method_includes_swing_daily_id():
    from trading_agent.strategy.multi_method import METHOD_IDS, EVALUATORS

    assert "swing_daily" in METHOD_IDS
    assert "swing_daily" in EVALUATORS


def test_desk_scanners_fixture_skips_network():
    from trading_agent.session.scanners import run_desk_scanners

    res = run_desk_scanners(
        slot="research",
        symbols=["SPY", "QQQ"],
        fixture_mode=True,
        post_discord=False,
    )
    assert "Fixture" in res.swing_text or "fixture" in res.swing_text.lower()
    assert res.combined_message()
    evening = run_desk_scanners(slot="evening", fixture_mode=True, post_discord=False)
    assert evening.slot == "evening"


def test_format_swing_scan_discord_play_and_empty():
    from trading_agent.strategy.swing_scan import (
        SwingCandidate,
        format_swing_scan_discord,
        post_swing_scan_to_discord,
    )

    empty = format_swing_scan_discord([])
    assert "Daily swing scan" in empty
    assert "No PLAY" in empty

    plays = [
        SwingCandidate(
            symbol="NVDA",
            play=True,
            side="CALL",
            score=72.0,
            style="both",
            pattern_name="bull_flag",
            entry=120.0,
            stop=115.0,
            target=130.0,
            atr_pct=2.5,
            trend="up",
            rs_score=4.0,
            reasons=["structure long"],
            asof="2026-08-11",
        )
    ]
    body = format_swing_scan_discord(plays)
    assert "NVDA" in body
    assert "CALL" in body
    assert "```" in body

    # Without Discord env, post should soft-fail not raise
    status = post_swing_scan_to_discord(plays)
    assert "ok" in status
    assert status.get("body")
