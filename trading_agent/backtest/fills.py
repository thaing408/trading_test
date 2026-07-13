"""Deterministic fill / exit model for offline ranking of configs.

Assumptions (labeled in reports):
- Entries at decision-day close.
- Directional long: stop below / target above; short inverted.
- Neutral strategies: small premium capture if price stays inside ATR band,
  else loss capped at risk unit. Strong trends raise breakout risk.
- Exit on first stop/target hit over hold_bars, else mark-to-market at hold end.
- No slippage, commissions, or options Greeks decay — relative ranking only.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple


def simulate_directional_exit(
    entry: float,
    stop: float,
    target: float,
    future_highs: Sequence[float],
    future_lows: Sequence[float],
    future_closes: Sequence[float],
    *,
    bullish: bool,
) -> Tuple[float, str, int]:
    """Return (exit_price, reason, bars_held)."""
    if not future_closes:
        return entry, "no_forward_bars", 0

    for i, (h, l, c) in enumerate(zip(future_highs, future_lows, future_closes)):
        if bullish:
            if l <= stop:
                return stop, "stop_loss", i + 1
            if h >= target:
                return target, "profit_target", i + 1
        else:
            if h >= stop:
                return stop, "stop_loss", i + 1
            if l <= target:
                return target, "profit_target", i + 1
    return float(future_closes[-1]), "time_exit", len(future_closes)


def simulate_neutral_exit(
    entry: float,
    risk_unit: float,
    future_highs: Sequence[float],
    future_lows: Sequence[float],
    future_closes: Sequence[float],
    band_pct: float = 0.015,
    *,
    trend_strength: float = 0.0,
) -> Tuple[float, str, int]:
    """Credit/neutral: win small if range stays inside band; lose risk_unit if breakout."""
    if not future_closes:
        return entry, "no_forward_bars", 0
    effective_band = max(0.008, band_pct - min(0.01, abs(trend_strength) * 0.02))
    upper = entry * (1 + effective_band)
    lower = entry * (1 - effective_band)
    for i, (h, l, c) in enumerate(zip(future_highs, future_lows, future_closes)):
        if h > upper or l < lower:
            return entry - risk_unit, "range_break", i + 1
    return entry + risk_unit * 0.45, "premium_capture", len(future_closes)


def pnl_dollars(
    entry: float,
    exit_price: float,
    *,
    bullish: bool,
    risk_dollars: float,
    stop: float,
    exit_reason: str = "",
) -> float:
    """Scale P/L so full stop ≈ -risk_dollars.

    Invariant: stop_loss exits never produce positive P/L for a correctly oriented book.
    """
    if bullish:
        move = exit_price - entry
        stop_dist = max(entry - stop, entry * 0.005)
    else:
        move = entry - exit_price
        stop_dist = max(stop - entry, entry * 0.005)
    if stop_dist <= 0:
        # Mis-oriented stop geometry — treat as full loss rather than phantom gain
        if exit_reason == "stop_loss":
            return round(-abs(risk_dollars), 2)
        return 0.0
    pl = risk_dollars * (move / stop_dist)
    if exit_reason == "stop_loss" and pl > 0:
        pl = -abs(risk_dollars)
    return round(pl, 2)


def max_drawdown_from_equity(equity: List[float]) -> float:
    if not equity:
        return 0.0
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        peak = max(peak, v)
        dd = peak - v
        max_dd = max(max_dd, dd)
    return round(max_dd, 2)
