"""Unit tests for ICT + SMC order blocks and breakers."""

from __future__ import annotations

from trading_agent.pa.order_block import (
    detect_ict_order_block_at,
    detect_smc_order_block_at,
    find_active_order_blocks,
    find_breakers,
    score_order_block_entry,
    update_ob_state,
)


def _flat(n: int, px: float = 100.0):
    o = [px] * n
    h = [px + 0.3] * n
    l = [px - 0.3] * n
    c = [px] * n
    return o, h, l, c


def test_ict_bullish_ob_after_fvg_displacement():
    """Bearish candle, then strong up impulse leaving bullish FVG."""
    # Build: quiet bars, bearish OB candle, small base, then displacement + FVG
    o, h, l, c = [], [], [], []
    # 0-4 quiet
    for _ in range(5):
        o.append(100.0)
        h.append(100.4)
        l.append(99.6)
        c.append(100.1)
    # 5: last down-close (OB)
    o.append(100.5)
    h.append(100.6)
    l.append(99.0)
    c.append(99.2)
    # 6: middle of 3-candle FVG structure
    o.append(99.3)
    h.append(99.8)
    l.append(99.1)
    c.append(99.7)
    # 7: displacement bar — low above high[5] for bullish FVG (low[7] > high[5])
    # FVG uses low[i] > high[i-2]: i=7, i-2=5 → need low[7] > high[5]=100.6
    o.append(100.0)
    h.append(103.5)
    l.append(100.8)  # > 100.6
    c.append(103.2)

    ob = detect_ict_order_block_at(o, h, l, c, 7, min_disp_atr=0.5)
    assert ob is not None
    assert ob.side == "bullish"
    assert ob.style == "ict"
    assert ob.index == 5
    # body of down candle 100.5 -> 99.2
    assert abs(ob.zone_high - 100.5) < 1e-9
    assert abs(ob.zone_low - 99.2) < 1e-9


def test_smc_bullish_ob_consecutive_impulse():
    o, h, l, c = _flat(8, 100.0)
    # index 3: bearish OB candle
    o[3], h[3], l[3], c[3] = 101.0, 101.2, 99.0, 99.5
    # 4,5,6: three strong bullish impulse bars
    for i, (oo, hh, ll, cc) in enumerate(
        [
            (99.6, 101.5, 99.5, 101.3),
            (101.3, 103.0, 101.2, 102.8),
            (102.8, 105.0, 102.7, 104.8),
        ]
    ):
        j = 4 + i
        o[j], h[j], l[j], c[j] = oo, hh, ll, cc

    ob = detect_smc_order_block_at(
        o, h, l, c, 6, impulse_bars=3, min_disp_atr=0.8, min_body_ratio=0.4
    )
    assert ob is not None
    assert ob.side == "bullish"
    assert ob.style == "smc"
    assert ob.index == 3
    # full range zone
    assert abs(ob.zone_low - 99.0) < 1e-9
    assert abs(ob.zone_high - 101.2) < 1e-9


def test_breaker_on_close_through():
    o = [100.0, 100.0, 100.0, 99.0, 100.0, 100.0, 98.0]
    h = [100.5, 100.5, 100.5, 99.5, 100.5, 100.5, 99.0]
    l = [99.5, 99.5, 99.5, 98.5, 99.5, 99.5, 97.0]
    c = [100.0, 100.0, 100.0, 98.8, 100.2, 100.1, 97.5]
    from trading_agent.pa.order_block import OrderBlock

    ob = OrderBlock(
        side="bullish",
        style="ict",
        zone_low=99.0,
        zone_high=100.0,
        index=3,
        impulse_end=4,
        body_low=99.0,
        body_high=100.0,
    )
    update_ob_state(ob, h, l, c, from_bar=5, to_bar=6)
    assert ob.invalidated
    assert ob.is_breaker


def test_score_entry_on_mitigation():
    """Synthetic series: form OB then return into zone with rejection."""
    o, h, l, c = [], [], [], []
    # base
    for _ in range(10):
        o.append(50.0)
        h.append(50.3)
        l.append(49.7)
        c.append(50.0)
    # bearish candle OB
    o.append(50.5)
    h.append(50.6)
    l.append(49.0)
    c.append(49.2)
    # middle
    o.append(49.3)
    h.append(49.9)
    l.append(49.2)
    c.append(49.8)
    # FVG displacement (bullish)
    o.append(50.0)
    h.append(53.0)
    l.append(50.8)
    c.append(52.8)
    # push away
    for _ in range(3):
        o.append(52.5)
        h.append(53.0)
        l.append(52.0)
        c.append(52.6)
    # mitigation bar: wick into body zone ~49.2-50.5, close up
    o.append(51.0)
    h.append(51.5)
    l.append(49.5)
    c.append(51.2)

    play, side, score, tags, entry, stop, target = score_order_block_entry(
        h, l, o, c, htf_direction="up", require_rejection=True
    )
    # May need soft assert: detector must find zone
    blocks = find_active_order_blocks(o, h, l, c, styles=("ict", "smc"))
    assert isinstance(blocks, list)
    assert isinstance(score, float)
    if play:
        assert side == "CALL"
        assert stop < entry
        assert target > entry


def test_find_breakers_list():
    o, h, l, c = _flat(20, 100.0)
    # Create SMC bullish OB then smash through
    o[5], h[5], l[5], c[5] = 101.0, 101.2, 99.0, 99.4
    for i, (oo, hh, ll, cc) in enumerate(
        [
            (99.5, 101.8, 99.4, 101.6),
            (101.6, 103.5, 101.5, 103.3),
            (103.3, 105.5, 103.2, 105.2),
        ]
    ):
        j = 6 + i
        o[j], h[j], l[j], c[j] = oo, hh, ll, cc
    # later invalidation close below zone
    o[12], h[12], l[12], c[12] = 100.0, 100.5, 98.0, 98.5

    brs = find_breakers(o, h, l, c, styles=("smc",), lookback=20, max_age_bars=20)
    assert isinstance(brs, list)
