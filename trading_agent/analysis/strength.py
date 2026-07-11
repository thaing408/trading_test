"""Pure strength/momentum metrics and gates (Komar-style, no I/O).

All functions operate on OHLCV sequences so unit tests need no network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from trading_agent.analysis.technical import ema
from trading_agent.screener_params import BestWinnersParams, PreMarketParams, get_screener_params


@dataclass
class StrengthMetrics:
    """Computed strength metrics for a single symbol."""

    price: float
    adr_pct: float
    pct_above_52w_low: float
    ema_8: float
    ema_21: float
    performance_3m_pct: float
    dollar_volume_avg_30d: float
    dollar_volume_prior_day: float
    low_52w: float
    gap_pct: float = 0.0
    relative_volume: float = 0.0


@dataclass
class StrengthEvaluation:
    passed: bool
    reasons: List[str] = field(default_factory=list)
    metrics: Optional[StrengthMetrics] = None


def average_daily_range_pct(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    lookback: int = 20,
) -> float:
    """ADR% = mean((high - low) / close * 100) over lookback bars."""
    n = min(len(closes), len(highs), len(lows), lookback)
    if n < 1:
        return 0.0
    h = list(highs)[-n:]
    l = list(lows)[-n:]
    c = list(closes)[-n:]
    total = 0.0
    for hi, lo, cl in zip(h, l, c):
        if cl <= 0:
            continue
        total += (float(hi) - float(lo)) / float(cl) * 100.0
    return round(total / n, 4)


def pct_above_52w_low(price: float, lows: Sequence[float]) -> float:
    """Percent distance of price above the lowest low in the series (proxy for 52w)."""
    if not lows or price <= 0:
        return 0.0
    low = float(min(lows))
    if low <= 0:
        return 0.0
    return round((float(price) - low) / low * 100.0, 4)


def performance_pct(closes: Sequence[float], lookback: int = 63) -> float:
    """Return over lookback bars (default ~3 months). Positive means up."""
    if len(closes) < 2:
        return 0.0
    end = float(closes[-1])
    if len(closes) <= lookback:
        start = float(closes[0])
    else:
        start = float(closes[-lookback])
    if start <= 0:
        return 0.0
    return round((end / start - 1.0) * 100.0, 4)


def dollar_volume(price: float, volume: float) -> float:
    return float(price) * float(volume)


def avg_dollar_volume(
    closes: Sequence[float],
    volumes: Sequence[float],
    lookback: int = 30,
) -> float:
    n = min(len(closes), len(volumes), lookback)
    if n < 1:
        return 0.0
    c = list(closes)[-n:]
    v = list(volumes)[-n:]
    return round(sum(float(ci) * float(vi) for ci, vi in zip(c, v)) / n, 2)


def prior_day_dollar_volume(closes: Sequence[float], volumes: Sequence[float]) -> float:
    if len(closes) < 2 or len(volumes) < 2:
        if closes and volumes:
            return dollar_volume(closes[-1], volumes[-1])
        return 0.0
    # Prior completed day = second-to-last bar when last is "today"
    return dollar_volume(closes[-2], volumes[-2])


def gap_pct_from_bars(
    opens: Sequence[float] | None,
    closes: Sequence[float],
) -> float:
    """Gap% = (today_open - prior_close) / prior_close * 100. Zero if opens missing."""
    if not opens or len(opens) < 1 or len(closes) < 2:
        return 0.0
    prior_close = float(closes[-2])
    today_open = float(opens[-1])
    if prior_close <= 0:
        return 0.0
    return round((today_open / prior_close - 1.0) * 100.0, 4)


def compute_strength_metrics(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    volumes: Sequence[float],
    *,
    opens: Sequence[float] | None = None,
    relative_volume: float = 0.0,
    gap_pct: float | None = None,
    params: BestWinnersParams | None = None,
) -> StrengthMetrics:
    p = params or get_screener_params().best_winners
    price = float(closes[-1]) if closes else 0.0
    e8 = ema(list(closes), p.ema_fast) if closes else 0.0
    e21 = ema(list(closes), p.ema_slow) if closes else 0.0
    low_52 = float(min(lows)) if lows else 0.0
    g = gap_pct if gap_pct is not None else gap_pct_from_bars(opens, closes)
    return StrengthMetrics(
        price=price,
        adr_pct=average_daily_range_pct(highs, lows, closes, p.adr_lookback),
        pct_above_52w_low=pct_above_52w_low(price, lows),
        ema_8=round(e8, 4),
        ema_21=round(e21, 4),
        performance_3m_pct=performance_pct(closes, p.performance_lookback_bars),
        dollar_volume_avg_30d=avg_dollar_volume(closes, volumes, p.avg_volume_lookback),
        dollar_volume_prior_day=prior_day_dollar_volume(closes, volumes),
        low_52w=low_52,
        gap_pct=g,
        relative_volume=float(relative_volume),
    )


def evaluate_strength_gates(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    volumes: Sequence[float],
    *,
    opens: Sequence[float] | None = None,
    relative_volume: float = 0.0,
    gap_pct: float | None = None,
    params: BestWinnersParams | None = None,
) -> StrengthEvaluation:
    """Apply Best Winners strength gates; each failure names the gate in reasons."""
    p = params or get_screener_params().best_winners
    if not closes or not highs or not lows or not volumes:
        return StrengthEvaluation(
            passed=False,
            reasons=["OHLCV unavailable — cannot evaluate strength gates"],
            metrics=None,
        )

    m = compute_strength_metrics(
        closes,
        highs,
        lows,
        volumes,
        opens=opens,
        relative_volume=relative_volume,
        gap_pct=gap_pct,
        params=p,
    )
    reasons: List[str] = []

    if m.price < p.min_price:
        reasons.append(
            f"Price ${m.price:.2f} below strength min ${p.min_price:.2f}"
        )
    if m.adr_pct < p.min_adr_pct:
        reasons.append(
            f"ADR% {m.adr_pct:.2f} below minimum {p.min_adr_pct} (volatility gate)"
        )
    if m.pct_above_52w_low < p.min_pct_above_52w_low:
        reasons.append(
            f"52w strength {m.pct_above_52w_low:.1f}% above low "
            f"(need ≥{p.min_pct_above_52w_low}%)"
        )
    if p.require_price_above_ema_fast and m.price < m.ema_8:
        reasons.append(
            f"Price ${m.price:.2f} below EMA{p.ema_fast} ${m.ema_8:.2f}"
        )
    if p.require_price_above_ema_slow and m.price < m.ema_21:
        reasons.append(
            f"Price ${m.price:.2f} below EMA{p.ema_slow} ${m.ema_21:.2f}"
        )
    if m.performance_3m_pct <= p.min_performance_3m_pct:
        reasons.append(
            f"3m performance {m.performance_3m_pct:.2f}% "
            f"(need >{p.min_performance_3m_pct}%)"
        )
    if m.dollar_volume_avg_30d < p.min_dollar_volume_avg_30d:
        reasons.append(
            f"Dollar volume avg30d ${m.dollar_volume_avg_30d:,.0f} "
            f"below ${p.min_dollar_volume_avg_30d:,.0f}"
        )
    if m.dollar_volume_prior_day < p.min_dollar_volume_prior_day:
        reasons.append(
            f"Dollar volume prior day ${m.dollar_volume_prior_day:,.0f} "
            f"below ${p.min_dollar_volume_prior_day:,.0f}"
        )

    return StrengthEvaluation(passed=len(reasons) == 0, reasons=reasons, metrics=m)


def evaluate_premarket_gates(
    metrics: StrengthMetrics,
    *,
    strength_eval: StrengthEvaluation | None = None,
    params: PreMarketParams | None = None,
    strength_params: BestWinnersParams | None = None,
) -> StrengthEvaluation:
    """Pre-market: strength gates (optional) + gap-up + unusual relative volume.

    Failures name the gate. auto_buy is never implied — observe/prepare only.
    """
    pm = params or get_screener_params().pre_market
    reasons: List[str] = []

    if pm.apply_strength_gates:
        if strength_eval is None:
            # Re-check using metrics alone for dollar/ADR/etc. already computed
            # Caller should pass strength_eval when OHLCV was evaluated.
            reasons.append("Strength evaluation missing for pre-market path")
        elif not strength_eval.passed:
            reasons.extend(strength_eval.reasons)

    if metrics.gap_pct < pm.min_gap_pct:
        reasons.append(
            f"Gap {metrics.gap_pct:.2f}% below min {pm.min_gap_pct}% (gap-up gate)"
        )
    if metrics.relative_volume < pm.min_relative_volume:
        reasons.append(
            f"Relative volume {metrics.relative_volume:.2f} below "
            f"unusual-volume min {pm.min_relative_volume} (pre-market RVOL gate)"
        )

    # Dedupe while preserving order
    seen = set()
    unique: List[str] = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            unique.append(r)

    return StrengthEvaluation(
        passed=len(unique) == 0,
        reasons=unique,
        metrics=metrics,
    )
