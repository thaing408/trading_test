"""Fair Value Gaps — shared geometry + fill scoring (multi-method ready).

Canonical 3-candle rule matches ``trading_agent.qt.model.detect_fvg``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple


@dataclass
class FairValueGap:
    side: str  # bullish | bearish
    gap_low: float
    gap_high: float
    index: int  # index of 3rd candle
    size_pct: float = 0.0
    fill_pct: float = 0.0
    filled: bool = False
    inverted: bool = False
    notes: List[str] = field(default_factory=list)

    @property
    def mid(self) -> float:
        return (self.gap_low + self.gap_high) / 2.0


def detect_fvg(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    i: int,
) -> Optional[Tuple[str, float, float]]:
    """3-candle FVG ending at index i.

    Bullish: low[i] > high[i-2]
    Bearish: high[i] < low[i-2]
    Returns (side, gap_low, gap_high).
    """
    if i < 2:
        return None
    if float(lows[i]) > float(highs[i - 2]):
        return ("bullish", float(highs[i - 2]), float(lows[i]))
    if float(highs[i]) < float(lows[i - 2]):
        return ("bearish", float(highs[i]), float(lows[i - 2]))
    return None


def detect_fvg_at(
    highs: Sequence[float],
    lows: Sequence[float],
    i: int,
    *,
    mid: Optional[float] = None,
) -> Optional[FairValueGap]:
    """Object form with size_pct."""
    dummy_o = [0.0] * len(highs)
    dummy_c = [0.0] * len(highs)
    raw = detect_fvg(dummy_o, highs, lows, dummy_c, i)
    if not raw:
        return None
    side, glo, ghi = raw
    ref = mid if mid and mid > 0 else (glo + ghi) / 2.0
    size_pct = abs(ghi - glo) / ref * 100.0 if ref > 0 else 0.0
    return FairValueGap(side=side, gap_low=glo, gap_high=ghi, index=i, size_pct=size_pct)


def fvg_fill_pct(
    gap: FairValueGap,
    highs: Sequence[float],
    lows: Sequence[float],
    start: int,
    end: int,
) -> float:
    """0–100 how much of the gap was traded through after formation."""
    if gap.gap_high <= gap.gap_low:
        return 0.0
    height = gap.gap_high - gap.gap_low
    if gap.side == "bullish":
        # fill from top down: how low did price go into the gap
        deepest = gap.gap_high
        for j in range(max(start, gap.index + 1), min(end + 1, len(lows))):
            deepest = min(deepest, float(lows[j]))
        if deepest >= gap.gap_high:
            return 0.0
        if deepest <= gap.gap_low:
            return 100.0
        return max(0.0, min(100.0, (gap.gap_high - deepest) / height * 100.0))
    # bearish: fill from bottom up
    highest = gap.gap_low
    for j in range(max(start, gap.index + 1), min(end + 1, len(highs))):
        highest = max(highest, float(highs[j]))
    if highest <= gap.gap_low:
        return 0.0
    if highest >= gap.gap_high:
        return 100.0
    return max(0.0, min(100.0, (highest - gap.gap_low) / height * 100.0))


def ifvg_confirm(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    side: str,
    start: int,
    end: int,
) -> bool:
    """True if FVG forms then price trades back through it (inverse) in window."""
    for i in range(max(start, 2), end + 1):
        fvg = detect_fvg(opens, highs, lows, closes, i)
        if not fvg:
            continue
        fside, glo, ghi = fvg
        if side in ("long", "CALL", "bullish") and fside == "bullish":
            for j in range(i + 1, min(end + 1, len(closes))):
                if float(lows[j]) <= glo:
                    return True
        if side in ("short", "PUT", "bearish") and fside == "bearish":
            for j in range(i + 1, min(end + 1, len(closes))):
                if float(highs[j]) >= ghi:
                    return True
    return False


def find_active_fvgs(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    lookback: int = 40,
    min_size_pct: float = 0.05,
    max_age_bars: int = 30,
) -> List[FairValueGap]:
    """Recent FVGs still relevant (not fully filled, size filter, age filter)."""
    n = len(closes)
    if n < 3:
        return []
    start = max(2, n - lookback)
    out: List[FairValueGap] = []
    mid = float(closes[-1]) if closes else 0.0
    for i in range(start, n):
        gap = detect_fvg_at(highs, lows, i, mid=mid)
        if not gap or gap.size_pct < min_size_pct:
            continue
        age = n - 1 - i
        if age > max_age_bars:
            continue
        fill = fvg_fill_pct(gap, highs, lows, i + 1, n - 1)
        gap.fill_pct = fill
        gap.filled = fill >= 99.0
        if gap.filled:
            # check inversion: close beyond far side after fill
            if gap.side == "bullish" and float(closes[-1]) < gap.gap_low:
                gap.inverted = True
            if gap.side == "bearish" and float(closes[-1]) > gap.gap_high:
                gap.inverted = True
            continue  # fully filled — skip as active entry zone unless IFVG handled elsewhere
        out.append(gap)
    return out[-12:]


def score_fvg_entry(
    highs: Sequence[float],
    lows: Sequence[float],
    opens: Sequence[float],
    closes: Sequence[float],
    *,
    htf_direction: str = "",  # up | down | range | ""
    min_size_pct: float = 0.08,
    require_rejection: bool = True,
) -> Tuple[bool, str, float, List[str], float, float, float]:
    """Score current bar for FVG pullback entry.

    Returns (play, side CALL|PUT|"", score, tags, entry, stop, target).
    """
    from trading_agent.pa.reactions import rejection_at_level

    n = len(closes)
    if n < 5:
        return False, "", 0.0, [], 0.0, 0.0, 0.0
    i = n - 1
    active = find_active_fvgs(
        highs, lows, closes, lookback=50, min_size_pct=min_size_pct, max_age_bars=40
    )
    if not active:
        return False, "", 15.0, [], 0.0, 0.0, 0.0

    c = float(closes[i])
    h = float(highs[i])
    l = float(lows[i])
    o = float(opens[i]) if opens else float(closes[i - 1])
    tags: List[str] = []
    best = None
    best_score = 0.0
    side = ""

    for gap in reversed(active):
        # price must interact with gap
        touches = l <= gap.gap_high and h >= gap.gap_low
        if not touches:
            continue
        # HTF alignment soft
        aligned = True
        if htf_direction == "up" and gap.side != "bullish":
            aligned = False
        if htf_direction == "down" and gap.side != "bearish":
            aligned = False
        if htf_direction == "range":
            aligned = True  # allow both in range

        rej_side = "long" if gap.side == "bullish" else "short"
        rejected = rejection_at_level(h, l, o, c, gap.mid, side=rej_side)
        if require_rejection and not rejected:
            # partial: still in gap with directional close
            if gap.side == "bullish" and not (c > o and c >= gap.gap_low):
                continue
            if gap.side == "bearish" and not (c < o and c <= gap.gap_high):
                continue

        score = 50.0 + min(25.0, gap.size_pct * 5.0)
        score += max(0.0, 20.0 - gap.fill_pct * 0.15)  # prefer less filled
        if rejected:
            score += 15.0
            tags.append("rejection")
        if aligned and htf_direction in ("up", "down"):
            score += 10.0
            tags.append(f"htf_{htf_direction}")
        elif htf_direction in ("up", "down") and not aligned:
            score -= 25.0
            tags.append("htf_against")
        tags.append(f"fvg_{gap.side}")
        tags.append(f"fill={gap.fill_pct:.0f}%")
        if score > best_score:
            best_score = score
            best = gap
            side = "CALL" if gap.side == "bullish" else "PUT"

    if best is None:
        return False, "", 20.0, ["no_fvg_touch"], 0.0, 0.0, 0.0

    entry = c
    if side == "CALL":
        stop = best.gap_low * 0.998
        target = entry + (entry - stop) * 1.5
    else:
        stop = best.gap_high * 1.002
        target = entry - (stop - entry) * 1.5
    play = best_score >= 55.0 and side in ("CALL", "PUT")
    if htf_direction == "up" and side == "PUT":
        play = False
    if htf_direction == "down" and side == "CALL":
        play = False
    return play, side, min(100.0, best_score), tags, entry, stop, target
