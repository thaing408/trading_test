"""Pure range-edge fade playbook (not Soulz multi-tag confluence)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from trading_agent.pa.reactions import rejection_at_level


@dataclass
class RangeFadeSignal:
    side: str
    range_high: float
    range_low: float
    entry: float
    stop: float
    target: float
    notes: List[str] = field(default_factory=list)


def evaluate_range_fade(
    highs: Sequence[float],
    lows: Sequence[float],
    opens: Sequence[float],
    closes: Sequence[float],
    *,
    lookback: int = 24,
    edge_frac: float = 0.15,
    min_height_pct: float = 0.2,
) -> Optional[RangeFadeSignal]:
    """Fade only at edges with rejection; target mid-range."""
    n = len(closes)
    if n < lookback + 1:
        return None
    i = n - 1
    # prior window for box
    rh = max(float(x) for x in highs[i - lookback : i])
    rl = min(float(x) for x in lows[i - lookback : i])
    if rh <= rl:
        return None
    mid = (rh + rl) / 2.0
    height = rh - rl
    if mid <= 0 or (height / mid) * 100 < min_height_pct:
        return None
    edge = height * edge_frac
    h, l = float(highs[i]), float(lows[i])
    o = float(opens[i]) if opens else float(closes[i - 1])
    c = float(closes[i])

    # Long at bottom
    if l <= rl + edge and c < mid:
        if rejection_at_level(h, l, o, c, rl, side="long") or (c > o and c > rl):
            stop = min(l, rl) * 0.998
            return RangeFadeSignal(
                side="CALL",
                range_high=rh,
                range_low=rl,
                entry=c,
                stop=stop,
                target=mid,
                notes=[f"range fade long edge rl={rl:.2f} mid={mid:.2f}"],
            )
    # Short at top
    if h >= rh - edge and c > mid:
        if rejection_at_level(h, l, o, c, rh, side="short") or (c < o and c < rh):
            stop = max(h, rh) * 1.002
            return RangeFadeSignal(
                side="PUT",
                range_high=rh,
                range_low=rl,
                entry=c,
                stop=stop,
                target=mid,
                notes=[f"range fade short edge rh={rh:.2f} mid={mid:.2f}"],
            )
    return None
