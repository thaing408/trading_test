"""Objective market structure: pivots, HH/HL, BOS/CHoCH, regime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple


@dataclass
class Pivot:
    index: int
    price: float
    kind: str  # high | low


@dataclass
class StructureState:
    trend: str  # up | down | range | unknown
    last_bos: str = ""  # bullish | bearish | ""
    last_choch: str = ""  # bullish | bearish | ""
    swing_high: float = 0.0
    swing_low: float = 0.0
    pivots_high: List[Pivot] = field(default_factory=list)
    pivots_low: List[Pivot] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def pivot_highs_lows(
    highs: Sequence[float],
    lows: Sequence[float],
    *,
    left: int = 2,
    right: int = 2,
) -> Tuple[List[Pivot], List[Pivot]]:
    """Fractal pivots: high/low greater/less than `left` bars before and `right` after."""
    n = len(highs)
    ph: List[Pivot] = []
    pl: List[Pivot] = []
    if n < left + right + 1:
        return ph, pl
    for i in range(left, n - right):
        h = float(highs[i])
        l = float(lows[i])
        if all(h >= float(highs[i - k]) for k in range(1, left + 1)) and all(
            h > float(highs[i + k]) for k in range(1, right + 1)
        ):
            ph.append(Pivot(index=i, price=h, kind="high"))
        if all(l <= float(lows[i - k]) for k in range(1, left + 1)) and all(
            l < float(lows[i + k]) for k in range(1, right + 1)
        ):
            pl.append(Pivot(index=i, price=l, kind="low"))
    return ph, pl


def analyze_structure(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    left: int = 2,
    right: int = 2,
    range_lookback: int = 20,
) -> StructureState:
    """Classify trend via recent swing pivots; detect simple BOS/CHoCH."""
    ph, pl = pivot_highs_lows(highs, lows, left=left, right=right)
    state = StructureState(trend="unknown", pivots_high=ph[-8:], pivots_low=pl[-8:])
    if len(closes) < 5:
        state.notes.append("insufficient bars")
        return state

    # Rolling range box for chop detection
    lb = min(range_lookback, len(highs))
    rh = max(float(x) for x in highs[-lb:])
    rl = min(float(x) for x in lows[-lb:])
    mid = (rh + rl) / 2.0 if rh > rl else float(closes[-1])
    height_pct = ((rh - rl) / mid * 100.0) if mid > 0 else 0.0

    # Need at least 2 highs and 2 lows for HH/HL
    if len(ph) >= 2 and len(pl) >= 2:
        h1, h2 = ph[-2].price, ph[-1].price
        l1, l2 = pl[-2].price, pl[-1].price
        state.swing_high = h2
        state.swing_low = l2
        hh = h2 > h1
        hl = l2 > l1
        lh = h2 < h1
        ll = l2 < l1
        if hh and hl:
            state.trend = "up"
            state.notes.append("HH+HL")
        elif lh and ll:
            state.trend = "down"
            state.notes.append("LH+LL")
        elif height_pct < 1.5:
            state.trend = "range"
            state.notes.append(f"compressed range {height_pct:.2f}%")
        else:
            state.trend = "range"
            state.notes.append("mixed swings → range")
    else:
        # Fallback: close vs mid of lookback
        c = float(closes[-1])
        if height_pct < 1.2:
            state.trend = "range"
        elif c > mid:
            state.trend = "up"
        elif c < mid:
            state.trend = "down"
        else:
            state.trend = "range"
        state.swing_high = rh
        state.swing_low = rl
        state.notes.append("pivot-light fallback")

    # BOS: close beyond last swing in trend direction
    c = float(closes[-1])
    if state.swing_high > 0 and c > state.swing_high and state.trend in ("up", "range"):
        if state.trend == "down":
            state.last_choch = "bullish"
            state.notes.append("CHoCH bullish (close > swing high from down)")
        else:
            state.last_bos = "bullish"
            state.notes.append("BOS bullish")
    if state.swing_low > 0 and c < state.swing_low and state.trend in ("down", "range"):
        if state.trend == "up":
            state.last_choch = "bearish"
            state.notes.append("CHoCH bearish")
        else:
            state.last_bos = "bearish"
            state.notes.append("BOS bearish")

    # Refine: prior trend from pivots then CHoCH
    if len(ph) >= 2 and len(pl) >= 2:
        prior_up = ph[-2].price < ph[-1].price and pl[-2].price < pl[-1].price
        prior_down = ph[-2].price > ph[-1].price and pl[-2].price > pl[-1].price
        if prior_down and c > ph[-1].price:
            state.last_choch = "bullish"
        if prior_up and c < pl[-1].price:
            state.last_choch = "bearish"

    return state
