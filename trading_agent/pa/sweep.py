"""Failed breakout / liquidity sweep then reclaim."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence


@dataclass
class SweepSignal:
    side: str  # CALL | PUT
    level: float
    sweep_extreme: float
    index: int
    notes: List[str] = field(default_factory=list)


def detect_sweep_reclaim(
    highs: Sequence[float],
    lows: Sequence[float],
    opens: Sequence[float],
    closes: Sequence[float],
    *,
    level_high: float,
    level_low: float,
    i: Optional[int] = None,
    pierce_pct: float = 0.05,
) -> Optional[SweepSignal]:
    """Sweep of range/session high or low then close back inside = failed breakout.

    Long (CALL): pierce below level_low then close back above level_low.
    Short (PUT): pierce above level_high then close back below level_high.
    """
    if not closes:
        return None
    idx = i if i is not None else len(closes) - 1
    if idx < 1 or level_high <= level_low:
        return None
    h = float(highs[idx])
    l = float(lows[idx])
    c = float(closes[idx])
    o = float(opens[idx]) if opens else float(closes[idx - 1])
    pierce_lo = level_low * (1 - pierce_pct / 100.0)
    pierce_hi = level_high * (1 + pierce_pct / 100.0)

    # Bullish sweep of lows
    if l < level_low and l <= pierce_lo + (level_low - pierce_lo) and c > level_low and c >= o:
        return SweepSignal(
            side="CALL",
            level=level_low,
            sweep_extreme=l,
            index=idx,
            notes=[f"sweep low {l:.2f} < {level_low:.2f}, reclaim close {c:.2f}"],
        )
    # Bearish sweep of highs
    if h > level_high and h >= pierce_hi - (pierce_hi - level_high) and c < level_high and c <= o:
        return SweepSignal(
            side="PUT",
            level=level_high,
            sweep_extreme=h,
            index=idx,
            notes=[f"sweep high {h:.2f} > {level_high:.2f}, reject close {c:.2f}"],
        )
    return None


def detect_sweep_from_series(
    highs: Sequence[float],
    lows: Sequence[float],
    opens: Sequence[float],
    closes: Sequence[float],
    *,
    lookback: int = 20,
) -> Optional[SweepSignal]:
    """Use rolling lookback high/low as liquidity pool."""
    n = len(closes)
    if n < lookback + 2:
        return None
    i = n - 1
    # levels from prior bars only
    rh = max(float(x) for x in highs[i - lookback : i])
    rl = min(float(x) for x in lows[i - lookback : i])
    return detect_sweep_reclaim(
        highs, lows, opens, closes, level_high=rh, level_low=rl, i=i
    )
