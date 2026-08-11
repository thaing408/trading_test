"""Classical chart patterns — detect, score, and size entries (multi-method ready).

Patterns (Bulkowski-style geometry on fractal pivots):
  - double_top / double_bottom
  - head_and_shoulders / inverse_head_and_shoulders
  - ascending_triangle / descending_triangle (breakout)
  - bull_flag / bear_flag (impulse + consolidation break)

PLAY bias is on **confirmed break** of neckline / pattern boundary with a
measured-move target from pattern height. Pure OHLCV — no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from trading_agent.pa.structure import Pivot, pivot_highs_lows


@dataclass
class ChartPattern:
    """Detected classical pattern with geometry for risk."""

    name: str
    bias: str  # bullish | bearish
    status: str  # confirmed | approaching
    neckline: float
    pattern_high: float
    pattern_low: float
    height: float
    confidence: float  # 0–100 geometry quality
    pivot_indices: List[int] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def side(self) -> str:
        return "CALL" if self.bias == "bullish" else "PUT"


def _tol_ok(a: float, b: float, tol_pct: float) -> bool:
    mid = (abs(a) + abs(b)) / 2.0
    if mid <= 0:
        return abs(a - b) < 1e-9
    return abs(a - b) / mid * 100.0 <= tol_pct


def _series(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
) -> Tuple[List[float], List[float], List[float]]:
    return (
        [float(x) for x in highs],
        [float(x) for x in lows],
        [float(x) for x in closes],
    )


def detect_double_top(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    ph: Optional[List[Pivot]] = None,
    pl: Optional[List[Pivot]] = None,
    tol_pct: float = 1.5,
    min_bars_between: int = 3,
    max_bars_between: int = 40,
) -> Optional[ChartPattern]:
    """Two similar pivot highs with a valley; bearish if close < valley."""
    h, l, c = _series(highs, lows, closes)
    n = len(c)
    if n < 10:
        return None
    if ph is None or pl is None:
        ph, pl = pivot_highs_lows(h, l, left=2, right=2)
    if len(ph) < 2:
        return None

    best: Optional[ChartPattern] = None
    for i in range(len(ph) - 1):
        p1, p2 = ph[i], ph[i + 1]
        gap = p2.index - p1.index
        if gap < min_bars_between or gap > max_bars_between:
            continue
        if not _tol_ok(p1.price, p2.price, tol_pct):
            continue
        # Valley = lowest low between the two peaks
        seg_lo = l[p1.index : p2.index + 1]
        if not seg_lo:
            continue
        valley = min(seg_lo)
        peak = max(p1.price, p2.price)
        height = peak - valley
        if height <= 0 or peak <= 0:
            continue
        height_pct = height / peak * 100.0
        if height_pct < 0.4:
            continue
        conf = 55.0 + min(20.0, (tol_pct - abs(p1.price - p2.price) / peak * 100.0) * 5)
        conf += min(15.0, height_pct * 2.0)
        last = c[-1]
        # Prefer patterns that completed recently (2nd peak not ancient)
        age = n - 1 - p2.index
        if age > 25:
            conf -= 15.0
        status = "confirmed" if last < valley else "approaching"
        if status == "confirmed":
            conf += 12.0
        elif last <= valley + height * 0.15:
            conf += 5.0  # near neckline
        else:
            conf -= 10.0
        notes = [
            f"peaks {p1.price:.2f}/{p2.price:.2f}",
            f"neckline(valley)={valley:.2f}",
            status,
        ]
        pat = ChartPattern(
            name="double_top",
            bias="bearish",
            status=status,
            neckline=valley,
            pattern_high=peak,
            pattern_low=valley,
            height=height,
            confidence=min(95.0, conf),
            pivot_indices=[p1.index, p2.index],
            notes=notes,
        )
        if best is None or pat.confidence > best.confidence:
            best = pat
    return best


def detect_double_bottom(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    ph: Optional[List[Pivot]] = None,
    pl: Optional[List[Pivot]] = None,
    tol_pct: float = 1.5,
    min_bars_between: int = 3,
    max_bars_between: int = 40,
) -> Optional[ChartPattern]:
    """Two similar pivot lows with a peak; bullish if close > peak."""
    h, l, c = _series(highs, lows, closes)
    n = len(c)
    if n < 10:
        return None
    if ph is None or pl is None:
        ph, pl = pivot_highs_lows(h, l, left=2, right=2)
    if len(pl) < 2:
        return None

    best: Optional[ChartPattern] = None
    for i in range(len(pl) - 1):
        p1, p2 = pl[i], pl[i + 1]
        gap = p2.index - p1.index
        if gap < min_bars_between or gap > max_bars_between:
            continue
        if not _tol_ok(p1.price, p2.price, tol_pct):
            continue
        seg_hi = h[p1.index : p2.index + 1]
        if not seg_hi:
            continue
        peak = max(seg_hi)
        trough = min(p1.price, p2.price)
        height = peak - trough
        if height <= 0 or trough <= 0:
            continue
        height_pct = height / peak * 100.0
        if height_pct < 0.4:
            continue
        conf = 55.0 + min(20.0, (tol_pct - abs(p1.price - p2.price) / peak * 100.0) * 5)
        conf += min(15.0, height_pct * 2.0)
        age = n - 1 - p2.index
        if age > 25:
            conf -= 15.0
        last = c[-1]
        status = "confirmed" if last > peak else "approaching"
        if status == "confirmed":
            conf += 12.0
        elif last >= peak - height * 0.15:
            conf += 5.0
        else:
            conf -= 10.0
        pat = ChartPattern(
            name="double_bottom",
            bias="bullish",
            status=status,
            neckline=peak,
            pattern_high=peak,
            pattern_low=trough,
            height=height,
            confidence=min(95.0, conf),
            pivot_indices=[p1.index, p2.index],
            notes=[
                f"troughs {p1.price:.2f}/{p2.price:.2f}",
                f"neckline(peak)={peak:.2f}",
                status,
            ],
        )
        if best is None or pat.confidence > best.confidence:
            best = pat
    return best


def detect_head_and_shoulders(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    ph: Optional[List[Pivot]] = None,
    pl: Optional[List[Pivot]] = None,
    shoulder_tol_pct: float = 3.0,
) -> Optional[ChartPattern]:
    """Left shoulder / head / right shoulder with neckline under the valleys."""
    h, l, c = _series(highs, lows, closes)
    n = len(c)
    if n < 15:
        return None
    if ph is None or pl is None:
        ph, pl = pivot_highs_lows(h, l, left=2, right=2)
    if len(ph) < 3:
        return None

    best: Optional[ChartPattern] = None
    # Scan last few triples of pivot highs
    for i in range(max(0, len(ph) - 6), len(ph) - 2):
        ls, head, rs = ph[i], ph[i + 1], ph[i + 2]
        if not (ls.index < head.index < rs.index):
            continue
        if head.price <= ls.price or head.price <= rs.price:
            continue
        if not _tol_ok(ls.price, rs.price, shoulder_tol_pct):
            continue
        # Head clearly higher than shoulders
        shoulder_avg = (ls.price + rs.price) / 2.0
        if head.price < shoulder_avg * 1.008:
            continue
        # Valleys between shoulders and head
        v1_seg = l[ls.index : head.index + 1]
        v2_seg = l[head.index : rs.index + 1]
        if not v1_seg or not v2_seg:
            continue
        v1, v2 = min(v1_seg), min(v2_seg)
        neckline = (v1 + v2) / 2.0
        height = head.price - neckline
        if height <= 0:
            continue
        conf = 58.0
        conf += min(12.0, (shoulder_tol_pct - abs(ls.price - rs.price) / shoulder_avg * 100) * 2)
        conf += min(15.0, (head.price / shoulder_avg - 1.0) * 100.0 * 3)
        age = n - 1 - rs.index
        if age > 20:
            conf -= 12.0
        last = c[-1]
        status = "confirmed" if last < neckline else "approaching"
        if status == "confirmed":
            conf += 14.0
        elif last <= neckline + height * 0.12:
            conf += 4.0
        else:
            conf -= 8.0
        pat = ChartPattern(
            name="head_and_shoulders",
            bias="bearish",
            status=status,
            neckline=neckline,
            pattern_high=head.price,
            pattern_low=min(v1, v2),
            height=height,
            confidence=min(96.0, conf),
            pivot_indices=[ls.index, head.index, rs.index],
            notes=[
                f"LS={ls.price:.2f} H={head.price:.2f} RS={rs.price:.2f}",
                f"neckline={neckline:.2f}",
                status,
            ],
        )
        if best is None or pat.confidence > best.confidence:
            best = pat
    return best


def detect_inverse_head_and_shoulders(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    ph: Optional[List[Pivot]] = None,
    pl: Optional[List[Pivot]] = None,
    shoulder_tol_pct: float = 3.0,
) -> Optional[ChartPattern]:
    """Inverse H&S on pivot lows; bullish if close > neckline."""
    h, l, c = _series(highs, lows, closes)
    n = len(c)
    if n < 15:
        return None
    if ph is None or pl is None:
        ph, pl = pivot_highs_lows(h, l, left=2, right=2)
    if len(pl) < 3:
        return None

    best: Optional[ChartPattern] = None
    for i in range(max(0, len(pl) - 6), len(pl) - 2):
        ls, head, rs = pl[i], pl[i + 1], pl[i + 2]
        if not (ls.index < head.index < rs.index):
            continue
        if head.price >= ls.price or head.price >= rs.price:
            continue
        if not _tol_ok(ls.price, rs.price, shoulder_tol_pct):
            continue
        shoulder_avg = (ls.price + rs.price) / 2.0
        if head.price > shoulder_avg * 0.992:
            continue
        v1_seg = h[ls.index : head.index + 1]
        v2_seg = h[head.index : rs.index + 1]
        if not v1_seg or not v2_seg:
            continue
        v1, v2 = max(v1_seg), max(v2_seg)
        neckline = (v1 + v2) / 2.0
        height = neckline - head.price
        if height <= 0:
            continue
        conf = 58.0
        conf += min(12.0, (shoulder_tol_pct - abs(ls.price - rs.price) / max(shoulder_avg, 1e-9) * 100) * 2)
        conf += min(15.0, (1.0 - head.price / shoulder_avg) * 100.0 * 3)
        age = n - 1 - rs.index
        if age > 20:
            conf -= 12.0
        last = c[-1]
        status = "confirmed" if last > neckline else "approaching"
        if status == "confirmed":
            conf += 14.0
        elif last >= neckline - height * 0.12:
            conf += 4.0
        else:
            conf -= 8.0
        pat = ChartPattern(
            name="inverse_head_and_shoulders",
            bias="bullish",
            status=status,
            neckline=neckline,
            pattern_high=max(v1, v2),
            pattern_low=head.price,
            height=height,
            confidence=min(96.0, conf),
            pivot_indices=[ls.index, head.index, rs.index],
            notes=[
                f"LS={ls.price:.2f} H={head.price:.2f} RS={rs.price:.2f}",
                f"neckline={neckline:.2f}",
                status,
            ],
        )
        if best is None or pat.confidence > best.confidence:
            best = pat
    return best


def detect_ascending_triangle(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    lookback: int = 30,
    flat_tol_pct: float = 0.8,
) -> Optional[ChartPattern]:
    """Flat resistance + rising lows; bullish on close above resistance."""
    h, l, c = _series(highs, lows, closes)
    n = len(c)
    if n < lookback:
        return None
    sl = slice(n - lookback, n)
    hh = h[sl]
    ll = l[sl]
    # Resistance = max of last third highs cluster
    res = max(hh[-lookback // 3 :])
    # Check earlier highs also near resistance
    early_highs = hh[: lookback // 2]
    if not early_highs:
        return None
    near_res = sum(1 for x in early_highs if abs(x - res) / res * 100.0 <= flat_tol_pct * 2)
    if near_res < 2:
        return None
    # Rising lows: first half min < second half min
    mid = lookback // 2
    lo1 = min(ll[:mid])
    lo2 = min(ll[mid:])
    if lo2 <= lo1 * 1.001:
        return None
    height = res - lo1
    if height <= 0:
        return None
    last = c[-1]
    status = "confirmed" if last > res else "approaching"
    conf = 52.0 + min(18.0, (lo2 / lo1 - 1.0) * 100.0 * 4)
    if status == "confirmed":
        conf += 14.0
    elif last >= res * (1 - 0.003):
        conf += 6.0
    else:
        conf -= 8.0
    return ChartPattern(
        name="ascending_triangle",
        bias="bullish",
        status=status,
        neckline=res,
        pattern_high=res,
        pattern_low=lo1,
        height=height,
        confidence=min(90.0, conf),
        notes=[f"res={res:.2f} rising_lows {lo1:.2f}->{lo2:.2f}", status],
    )


def detect_descending_triangle(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    lookback: int = 30,
    flat_tol_pct: float = 0.8,
) -> Optional[ChartPattern]:
    """Flat support + falling highs; bearish on close below support."""
    h, l, c = _series(highs, lows, closes)
    n = len(c)
    if n < lookback:
        return None
    sl = slice(n - lookback, n)
    hh = h[sl]
    ll = l[sl]
    support = min(ll[-lookback // 3 :])
    early_lows = ll[: lookback // 2]
    near_sup = sum(
        1 for x in early_lows if abs(x - support) / max(support, 1e-9) * 100.0 <= flat_tol_pct * 2
    )
    if near_sup < 2:
        return None
    mid = lookback // 2
    hi1 = max(hh[:mid])
    hi2 = max(hh[mid:])
    if hi2 >= hi1 * 0.999:
        return None
    height = hi1 - support
    if height <= 0:
        return None
    last = c[-1]
    status = "confirmed" if last < support else "approaching"
    conf = 52.0 + min(18.0, (1.0 - hi2 / hi1) * 100.0 * 4)
    if status == "confirmed":
        conf += 14.0
    elif last <= support * (1 + 0.003):
        conf += 6.0
    else:
        conf -= 8.0
    return ChartPattern(
        name="descending_triangle",
        bias="bearish",
        status=status,
        neckline=support,
        pattern_high=hi1,
        pattern_low=support,
        height=height,
        confidence=min(90.0, conf),
        notes=[f"sup={support:.2f} falling_highs {hi1:.2f}->{hi2:.2f}", status],
    )


def detect_bull_flag(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    impulse_bars: int = 8,
    flag_bars: int = 10,
    min_impulse_pct: float = 1.5,
    max_flag_retrace: float = 0.55,
) -> Optional[ChartPattern]:
    """Sharp rise then tight pullback/range; bullish on break of flag high."""
    h, l, c = _series(highs, lows, closes)
    n = len(c)
    need = impulse_bars + flag_bars + 1
    if n < need:
        return None
    flag_start = n - flag_bars
    imp_start = flag_start - impulse_bars
    imp_open = c[imp_start]
    imp_high = max(h[imp_start:flag_start])
    imp_low = min(l[imp_start:flag_start])
    if imp_open <= 0:
        return None
    impulse_pct = (imp_high - imp_open) / imp_open * 100.0
    if impulse_pct < min_impulse_pct:
        return None
    # Flag: mild down/sideways after impulse
    flag_high = max(h[flag_start:])
    flag_low = min(l[flag_start:])
    flag_range = flag_high - flag_low
    impulse_h = imp_high - imp_low
    if impulse_h <= 0 or flag_range > impulse_h * max_flag_retrace * 1.5:
        return None
    # Prefer flag not fully retracing impulse
    if flag_low < imp_open + (imp_high - imp_open) * (1 - max_flag_retrace):
        # deep retrace — weak
        if flag_low < imp_open:
            return None
    last = c[-1]
    height = imp_high - imp_open
    status = "confirmed" if last > flag_high else "approaching"
    conf = 50.0 + min(20.0, impulse_pct * 2.0)
    if flag_range / max(imp_high, 1e-9) * 100 < 1.2:
        conf += 8.0  # tight flag
    if status == "confirmed":
        conf += 14.0
    else:
        conf -= 5.0
    return ChartPattern(
        name="bull_flag",
        bias="bullish",
        status=status,
        neckline=flag_high,
        pattern_high=imp_high,
        pattern_low=flag_low,
        height=height,
        confidence=min(92.0, conf),
        notes=[f"impulse={impulse_pct:.1f}% flag_hi={flag_high:.2f}", status],
    )


def detect_bear_flag(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    impulse_bars: int = 8,
    flag_bars: int = 10,
    min_impulse_pct: float = 1.5,
    max_flag_retrace: float = 0.55,
) -> Optional[ChartPattern]:
    """Sharp drop then tight bounce; bearish on break of flag low."""
    h, l, c = _series(highs, lows, closes)
    n = len(c)
    need = impulse_bars + flag_bars + 1
    if n < need:
        return None
    flag_start = n - flag_bars
    imp_start = flag_start - impulse_bars
    imp_open = c[imp_start]
    imp_high = max(h[imp_start:flag_start])
    imp_low = min(l[imp_start:flag_start])
    if imp_open <= 0:
        return None
    impulse_pct = (imp_open - imp_low) / imp_open * 100.0
    if impulse_pct < min_impulse_pct:
        return None
    flag_high = max(h[flag_start:])
    flag_low = min(l[flag_start:])
    flag_range = flag_high - flag_low
    impulse_h = imp_high - imp_low
    if impulse_h <= 0 or flag_range > impulse_h * max_flag_retrace * 1.5:
        return None
    if flag_high > imp_open - (imp_open - imp_low) * (1 - max_flag_retrace):
        if flag_high > imp_open:
            return None
    last = c[-1]
    height = imp_open - imp_low
    status = "confirmed" if last < flag_low else "approaching"
    conf = 50.0 + min(20.0, impulse_pct * 2.0)
    if flag_range / max(imp_low, 1e-9) * 100 < 1.2:
        conf += 8.0
    if status == "confirmed":
        conf += 14.0
    else:
        conf -= 5.0
    return ChartPattern(
        name="bear_flag",
        bias="bearish",
        status=status,
        neckline=flag_low,
        pattern_high=flag_high,
        pattern_low=imp_low,
        height=height,
        confidence=min(92.0, conf),
        notes=[f"impulse={impulse_pct:.1f}% flag_lo={flag_low:.2f}", status],
    )


def detect_all_chart_patterns(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    left: int = 2,
    right: int = 2,
) -> List[ChartPattern]:
    """Run all classical detectors; return sorted by confidence desc."""
    h, l, c = _series(highs, lows, closes)
    ph, pl = pivot_highs_lows(h, l, left=left, right=right)
    found: List[ChartPattern] = []
    for fn in (
        detect_double_top,
        detect_double_bottom,
        detect_head_and_shoulders,
        detect_inverse_head_and_shoulders,
        detect_ascending_triangle,
        detect_descending_triangle,
        detect_bull_flag,
        detect_bear_flag,
    ):
        try:
            # Pivot-based detectors accept ph/pl; triangle/flag ignore extras via kwargs only on some
            if fn in (
                detect_double_top,
                detect_double_bottom,
                detect_head_and_shoulders,
                detect_inverse_head_and_shoulders,
            ):
                pat = fn(h, l, c, ph=ph, pl=pl)
            else:
                pat = fn(h, l, c)
        except TypeError:
            pat = fn(h, l, c)
        if pat is not None:
            found.append(pat)
    found.sort(key=lambda p: p.confidence, reverse=True)
    return found


def score_chart_pattern_entry(
    highs: Sequence[float],
    lows: Sequence[float],
    opens: Sequence[float],
    closes: Sequence[float],
    *,
    htf_direction: str = "",
    require_confirmed: bool = True,
    min_confidence: float = 55.0,
    measured_move_r: float = 1.0,
) -> Tuple[bool, str, float, List[str], float, float, float]:
    """Score current bar for classical chart-pattern entry.

    Returns (play, side CALL|PUT|"", score, tags, entry, stop, target).
    Measured move: target = break ± height * measured_move_r.
    Stop beyond pattern extreme (high for shorts, low for longs).
    """
    n = len(closes)
    if n < 15:
        return False, "", 0.0, [], 0.0, 0.0, 0.0

    patterns = detect_all_chart_patterns(highs, lows, closes)
    if not patterns:
        return False, "", 12.0, ["no_chart_pattern"], 0.0, 0.0, 0.0

    c = float(closes[-1])
    tags: List[str] = []
    best: Optional[ChartPattern] = None
    best_score = 0.0

    for pat in patterns:
        if require_confirmed and pat.status != "confirmed":
            # Allow near-break with lower score path
            score_try = pat.confidence - 18.0
        else:
            score_try = pat.confidence

        # HTF soft alignment
        if htf_direction == "up" and pat.bias == "bearish":
            score_try -= 18.0
            tags.append("htf_against")
        elif htf_direction == "down" and pat.bias == "bullish":
            score_try -= 18.0
            tags.append("htf_against")
        elif htf_direction in ("up", "down") and (
            (htf_direction == "up" and pat.bias == "bullish")
            or (htf_direction == "down" and pat.bias == "bearish")
        ):
            score_try += 10.0
            tags.append(f"htf_{htf_direction}")

        # Prefer confirmed breakouts
        if pat.status == "confirmed":
            score_try += 5.0
            tags.append("confirmed_break")
        else:
            tags.append("approaching")

        # Height quality
        mid = (pat.pattern_high + pat.pattern_low) / 2.0 or c
        height_pct = pat.height / mid * 100.0 if mid else 0.0
        score_try += min(10.0, height_pct)

        tags.append(pat.name)
        tags.append(pat.bias)

        if score_try > best_score:
            best_score = score_try
            best = pat

    if best is None:
        return False, "", 15.0, ["no_pattern_scored"], 0.0, 0.0, 0.0

    # Rebuild clean tags for winner
    side = best.side
    entry = c
    if side == "CALL":
        stop = min(best.pattern_low, best.neckline) * 0.998
        risk = max(entry - stop, entry * 0.002)
        target = entry + best.height * measured_move_r
        if target <= entry:
            target = entry + risk * 1.5
    else:
        stop = max(best.pattern_high, best.neckline) * 1.002
        risk = max(stop - entry, entry * 0.002)
        target = entry - best.height * measured_move_r
        if target >= entry:
            target = entry - risk * 1.5

    win_tags = [best.name, best.bias, best.status, f"h={best.height:.2f}"]
    if htf_direction:
        win_tags.append(f"htf={htf_direction}")

    play = (
        best_score >= min_confidence
        and side in ("CALL", "PUT")
        and (best.status == "confirmed" or not require_confirmed)
    )
    # Strict HTF hard block when clearly against
    if htf_direction == "up" and side == "PUT" and best_score < 70:
        play = False
    if htf_direction == "down" and side == "CALL" and best_score < 70:
        play = False

    # Approaching-only: no play when require_confirmed
    if require_confirmed and best.status != "confirmed":
        play = False

    return (
        play,
        side if play or best_score >= 40 else "",
        min(100.0, max(0.0, best_score)),
        win_tags,
        entry,
        stop,
        target,
    )


def pattern_names_for_ta_gate(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
) -> List[str]:
    """Names suitable for discipline/ta_books opposing-pattern blocks."""
    return [p.name for p in detect_all_chart_patterns(highs, lows, closes)]
