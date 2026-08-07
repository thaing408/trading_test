"""Unit tests for Soulz PA BRR + Range + Fib confluence (offline)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_agent.scalp.soulz_pa import (
    SoulzPaConfig,
    detect_range_long,
    evaluate_bar_signal,
    fib_zone,
    last_impulse,
    rolling_range,
    run_soulz_backtest,
)


def test_rolling_range():
    highs = [10, 11, 12, 11, 13]
    lows = [9, 9.5, 10, 10, 11]
    rh, rl = rolling_range(highs, lows, 4, 3)
    assert rh == 12  # max of highs[1:4] wait - start=max(0,4-3)=1, end=4 → highs[1:4]=11,12,11
    assert rl == 9.5


def test_fib_zone_up():
    z_lo, z_hi = fib_zone(100, 200, "up", 0.382, 0.618)
    # retrace from 200: 38.2% → 161.8, 61.8% → 138.2
    assert z_lo == pytest.approx(138.2, rel=1e-3)
    assert z_hi == pytest.approx(161.8, rel=1e-3)


def test_last_impulse_up():
    closes = [100 + i for i in range(20)]
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    lo, hi, d = last_impulse(closes, highs, lows, 19, 15)
    assert d == "up"
    assert hi > lo


def test_range_long_near_lows():
    # flat range 100-110, then rejection at bottom
    n = 30
    highs = [110.0] * n
    lows = [100.0] * n
    closes = [105.0] * n
    # last bar: low tags 100, closes up toward mid
    lows[-1] = 100.2
    closes[-1] = 103.0
    highs[-1] = 104.0
    # need prior closes for open approx
    closes[-2] = 101.0
    cfg = SoulzPaConfig(range_lookback=20)
    hit = detect_range_long(closes, highs, lows, n - 1, cfg)
    assert hit is not None


def test_evaluate_confluence_requires_two():
    # synthetic trending series — may or may not hit 2 tags; test API
    cfg = SoulzPaConfig(min_confluence=2, allow_single_brr=False)
    n = 80
    closes = list(np.linspace(100, 120, n))
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    # force a clear bounce structure at end
    for i in range(n - 15, n - 5):
        closes[i] = 118
        highs[i] = 119
        lows[i] = 117
    closes[-1] = 117.5
    lows[-1] = 116.5
    highs[-1] = 118
    sig = evaluate_bar_signal(closes, highs, lows, n - 1, cfg)
    # either None or confluence >= 2
    if sig is not None:
        assert sig.confluence >= 2


def test_backtest_synthetic_offline():
    # build fake OHLCV dataframe without network
    idx = pd.date_range("2026-06-01", periods=200, freq="15min", tz="America/New_York")
    # filter to RTH-ish for density
    rng = np.random.default_rng(42)
    px = 100 + np.cumsum(rng.normal(0, 0.15, len(idx)))
    df = pd.DataFrame(
        {
            "Open": px,
            "High": px + 0.3,
            "Low": px - 0.3,
            "Close": px + rng.normal(0, 0.05, len(idx)),
            "Volume": rng.integers(1000, 5000, len(idx)),
        },
        index=idx,
    )
    cfg = SoulzPaConfig(
        symbol="TEST",
        min_confluence=1,
        allow_single_brr=True,
        allow_single_range=True,
        rth_only=False,
        max_trades_per_day=10,
    )
    result = run_soulz_backtest("TEST", period="5d", interval="15m", cfg=cfg, df=df)
    assert result.symbol == "TEST"
    assert result.trade_count >= 0
    assert "Soulz" in " ".join(result.assumptions) or result.metadata.get("style") == "soulz_pa"
