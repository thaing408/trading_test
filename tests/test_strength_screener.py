"""Unit tests for Komar-style strength/pre-market screener gates (real shipped code)."""

from __future__ import annotations

from trading_agent.analysis.strength import (
    average_daily_range_pct,
    evaluate_premarket_gates,
    evaluate_strength_gates,
    pct_above_52w_low,
    performance_pct,
)
from trading_agent.config import AgentConfig
from trading_agent.pipeline import run_pipeline
from trading_agent.screener_params import BestWinnersParams, get_screener_params


def _pass_bars(n: int = 80, end: float = 100.0, adr_pct: float = 5.5, vol: int = 2_000_000):
    """Synthetic OHLCV that satisfies default Best Winners gates."""
    low_anchor = end / 2.0
    closes, highs, lows, volumes = [], [], [], []
    for i in range(n):
        if i < 8:
            c = low_anchor * (1.0 + 0.02 * i)
        else:
            t2 = (i - 8) / (n - 1 - 8)
            c = low_anchor * 1.16 + (end - low_anchor * 1.16) * t2
        half = c * (adr_pct / 100.0) / 2.0
        closes.append(c)
        highs.append(c + half)
        lows.append(min(c - half, low_anchor) if i < 3 else c - half)
        volumes.append(vol)
    closes[-1] = end
    highs[-1] = end * (1 + adr_pct / 200)
    lows[-1] = end * (1 - adr_pct / 200)
    return closes, highs, lows, volumes


def test_screener_params_contain_source_thresholds():
    params = get_screener_params("soft")
    bw = params.best_winners
    pm = params.pre_market
    assert bw.market == "US"
    # Softened defaults (not classic Komar 4.5 / 70%)
    assert bw.min_adr_pct == 2.5
    assert bw.min_pct_above_52w_low == 35.0
    assert bw.ema_fast == 8
    assert bw.ema_slow == 21
    assert bw.require_price_above_ema_fast is True
    assert bw.require_price_above_ema_slow is False
    assert bw.min_performance_3m_pct == 0.0
    assert bw.min_dollar_volume_avg_30d == 10_000_000.0
    assert bw.min_dollar_volume_prior_day == 5_000_000.0
    assert pm.apply_strength_gates is True
    assert pm.auto_buy is False
    assert "gap" in pm.source.lower() or "volume" in pm.source.lower()
    d = params.to_dict()
    assert "best_winners" in d and "pre_market" in d
    assert d["best_winners"]["min_adr_pct"] == 2.5
    # Strict profile still available
    strict = get_screener_params("strict").best_winners
    assert strict.min_adr_pct == 4.5
    assert strict.min_pct_above_52w_low == 70.0
    assert strict.require_price_above_ema_slow is True


def test_pass_all_strength_gates():
    c, h, l, v = _pass_bars()
    result = evaluate_strength_gates(c, h, l, v)
    assert result.passed is True, result.reasons
    assert result.metrics is not None
    assert result.metrics.adr_pct >= 2.5
    assert result.metrics.pct_above_52w_low >= 35.0
    assert result.metrics.price > result.metrics.ema_8
    assert result.metrics.performance_3m_pct > 0
    assert result.metrics.dollar_volume_avg_30d >= 10_000_000
    assert result.metrics.dollar_volume_prior_day >= 5_000_000


def test_soft_defaults_pass_large_cap_like_profile():
    """ADR ~3.2, moderate 52w — fails classic 4.5/70, passes soft defaults."""
    from trading_agent.screener_params import SOFT_BEST_WINNERS, STRICT_BEST_WINNERS

    c, h, l, v = _pass_bars(n=80, end=100.0, adr_pct=3.2, vol=2_000_000)
    # Cap 52w: raise the series floor so pct_above_52w_low is moderate (~40-50%)
    # _pass_bars already builds from low_anchor = end/2 → ~100% above low; tighten lows
    floor = 100.0 / 1.45  # ~45% above 52w low at end=100
    l = [max(floor, x) for x in l]
    soft = evaluate_strength_gates(c, h, l, v, params=SOFT_BEST_WINNERS)
    strict = evaluate_strength_gates(c, h, l, v, params=STRICT_BEST_WINNERS)
    assert soft.passed is True, soft.reasons
    assert strict.passed is False, "strict should still reject this large-cap-like profile"
    assert any("ADR" in r or "52w" in r for r in strict.reasons)


def test_fail_adr_gate():
    c, h, l, v = _pass_bars(adr_pct=1.0)  # below soft 2.5 floor
    result = evaluate_strength_gates(c, h, l, v)
    assert result.passed is False
    assert any("ADR" in r for r in result.reasons)


def test_fail_52w_gate():
    # Flat series near the same level → pct above 52w low small
    closes = [100.0 + i * 0.01 for i in range(60)]
    highs = [c * 1.03 for c in closes]  # ADR ok-ish
    lows = [c * 0.97 for c in closes]
    volumes = [2_000_000] * 60
    # Widen ADR enough
    highs = [c + 3 for c in closes]
    lows = [c - 3 for c in closes]
    result = evaluate_strength_gates(closes, highs, lows, volumes)
    assert result.passed is False
    assert any("52w" in r for r in result.reasons)


def test_fail_ema_gate():
    # Strong downtrend: price below EMAs
    closes = [200.0 - i * 1.5 for i in range(80)]
    highs = [c * 1.03 for c in closes]
    lows = [c * 0.97 for c in closes]
    # Deep low at end so 52w can still fail or pass; force high early then crash
    closes = [50.0] * 5 + [50.0 + i for i in range(40)] + [200.0 - i for i in range(40)]
    # Rebuild: spike then reverse below EMAs
    base = list(range(50, 130))
    crash = list(range(129, 60, -1))
    closes = [float(x) for x in base + crash]
    highs = [c * 1.04 for c in closes]
    lows = [c * 0.96 for c in closes]
    lows[0] = min(lows) * 0.4  # ensure 52w distance high at mid, may still fail at end
    volumes = [3_000_000] * len(closes)
    result = evaluate_strength_gates(closes, highs, lows, volumes)
    assert result.passed is False
    # Downtrend should trip EMA and/or 3m performance
    assert any("EMA" in r or "3m" in r or "52w" in r for r in result.reasons)


def test_fail_performance_gate():
    # Declining series over the window
    closes = [150.0 - i * 0.5 for i in range(70)]
    highs = [c * 1.04 for c in closes]
    lows = [c * 0.9 for c in closes]  # deep lows for 52w
    lows = [min(closes) * 0.5] + [c * 0.96 for c in closes[1:]]
    volumes = [2_000_000] * len(closes)
    result = evaluate_strength_gates(closes, highs, lows, volumes)
    assert result.passed is False
    assert any("3m" in r or "performance" in r.lower() for r in result.reasons)


def test_fail_dollar_volume_gate():
    c, h, l, _ = _pass_bars(vol=100)  # tiny volume
    v = [100] * len(c)
    result = evaluate_strength_gates(c, h, l, v)
    assert result.passed is False
    assert any("Dollar volume" in r for r in result.reasons)


def test_premarket_requires_gap_and_rvol_when_checked():
    c, h, l, v = _pass_bars()
    strength = evaluate_strength_gates(c, h, l, v, relative_volume=0.5, gap_pct=-1.0)
    assert strength.passed is True
    assert strength.metrics is not None
    strength.metrics.relative_volume = 0.5
    strength.metrics.gap_pct = -1.0
    pre = evaluate_premarket_gates(strength.metrics, strength_eval=strength)
    assert pre.passed is False
    assert any("Gap" in r for r in pre.reasons)
    assert any("Relative volume" in r or "RVOL" in r for r in pre.reasons)


def test_pipeline_fixture_strength_rejections_name_gates():
    config = AgentConfig(fixture_mode=True, use_live_data=False)
    plan = run_pipeline(config)
    assert plan.top_watchlist or plan.rejection_reasons
    # Weak fixture names (AAPL/SPY/XLF) should appear with strength gate language
    strength_rejections = [
        r
        for r in plan.rejection_reasons
        if any(
            key in r.reason
            for key in ("ADR%", "52w", "EMA", "3m performance", "Dollar volume")
        )
    ]
    assert strength_rejections, (
        f"Expected named strength rejections, got: "
        f"{[(r.symbol, r.reason) for r in plan.rejection_reasons]}"
    )
    summary = plan.research_summary
    # Profile name is soft_* by default
    assert "best_winners" in str(summary.get("strength_profile") or "")
    assert summary.get("screener_params", {}).get("min_adr_pct") == 2.5
    assert summary.get("strength_rejected", 0) >= 1


def test_pipeline_strength_survivors_or_cash_rationale():
    config = AgentConfig(fixture_mode=True, use_live_data=False)
    plan = run_pipeline(config)
    summary = plan.research_summary
    # NVDA/AMD/TSLA should survive strength when OHLCV fixtures are strong
    if summary.get("strength_survivors", 0) > 0:
        assert any(s in plan.top_watchlist for s in ("NVDA", "AMD", "TSLA", "META", "MSFT")) or plan.ranked_opportunities
    else:
        assert plan.stay_in_cash
        assert "Strength" in plan.cash_recommendation_reason or any(
            "ADR" in r.reason or "52w" in r.reason for r in plan.rejection_reasons
        )


def test_metric_helpers_drive_real_formulas():
    closes = [100.0, 102.0, 101.0, 105.0]
    highs = [101.0, 104.0, 103.0, 108.0]
    lows = [99.0, 100.0, 100.0, 104.0]
    adr = average_daily_range_pct(highs, lows, closes, lookback=4)
    assert adr > 0
    assert pct_above_52w_low(108.0, lows) > 0
    assert performance_pct([50.0, 60.0, 70.0, 80.0], lookback=3) > 0


def test_custom_params_thresholds():
    c, h, l, v = _pass_bars(adr_pct=5.0)
    strict = BestWinnersParams(min_adr_pct=10.0)
    result = evaluate_strength_gates(c, h, l, v, params=strict)
    assert result.passed is False
    assert any("ADR" in r for r in result.reasons)
