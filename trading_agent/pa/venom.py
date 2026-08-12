"""ICT Venom Model v1 — mechanical NY open range-sweep (research).

Canonical intent: ICT 2025 Venom lecture (08:00–09:30 ET box → 09:30+ sweep
→ FVG/BPR + structure → entry → ~2R). This is a **rule-based approximation**,
not a transcript of ICT discretion.

Spec summary:
  - Venom Box = high/low of bars in [08:00, 09:30) America/New_York
  - After 09:30: sweep box high or low (wick beyond + reclaim close)
  - Confirmation: FVG and optional BPR (overlapping bull+bear FVG)
  - Entry A: retest of BPR mid (or FVG mid)
  - Entry B: engulfing candle that trades back through FVG
  - Stop beyond sweep extreme; target = entry ± 2R (or opposite box side)

Pure OHLCV + timestamps — no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from trading_agent.pa.fvg import FairValueGap, detect_fvg_at

ET = ZoneInfo("America/New_York")
BOX_START = time(8, 0)
BOX_END = time(9, 30)  # exclusive end of box window
RTH_OPEN = time(9, 30)
SESSION_END = time(11, 0)  # stop hunting new Venom entries after this


@dataclass
class VenomBox:
    session: date
    high: float
    low: float
    start_idx: int
    end_idx: int  # last bar index inside box

    @property
    def mid(self) -> float:
        return (self.high + self.low) / 2.0

    @property
    def height(self) -> float:
        return max(0.0, self.high - self.low)


@dataclass
class BalancedPriceRange:
    """BPR: overlapping bullish + bearish FVG zones."""

    low: float
    high: float
    bull_index: int
    bear_index: int

    @property
    def mid(self) -> float:
        return (self.low + self.high) / 2.0


@dataclass
class VenomSignal:
    side: str  # CALL | PUT
    entry_type: str  # bpr_retest | fvg_retest | venom_engulf
    entry: float
    stop: float
    target: float
    sweep_extreme: float
    box_high: float
    box_low: float
    index: int  # signal bar
    r_multiple: float = 2.0
    notes: List[str] = field(default_factory=list)

    @property
    def risk(self) -> float:
        return abs(self.entry - self.stop)


def _to_et(ts) -> datetime:
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            return ts.replace(tzinfo=ET)
        return ts.astimezone(ET)
    # pandas Timestamp
    try:
        t = ts.to_pydatetime()
        if t.tzinfo is None:
            return t.replace(tzinfo=ET)
        return t.astimezone(ET)
    except Exception:
        return datetime.now(ET)


def bar_in_window(ts, start: time, end: time) -> bool:
    """True if bar time in [start, end) ET."""
    t = _to_et(ts).time()
    if start <= end:
        return start <= t < end
    # overnight wrap (not used for Venom box)
    return t >= start or t < end


def find_session_indices(
    timestamps: Sequence,
    session: date,
) -> List[int]:
    out = []
    for i, ts in enumerate(timestamps):
        if _to_et(ts).date() == session:
            out.append(i)
    return out


def compute_venom_box(
    timestamps: Sequence,
    highs: Sequence[float],
    lows: Sequence[float],
    session: date,
) -> Optional[VenomBox]:
    """High/low of bars in [08:00, 09:30) ET on session day."""
    idxs = []
    for i, ts in enumerate(timestamps):
        et = _to_et(ts)
        if et.date() != session:
            continue
        if bar_in_window(ts, BOX_START, BOX_END):
            idxs.append(i)
    if len(idxs) < 2:
        return None
    hi = max(float(highs[i]) for i in idxs)
    lo = min(float(lows[i]) for i in idxs)
    if hi <= lo:
        return None
    return VenomBox(
        session=session,
        high=hi,
        low=lo,
        start_idx=idxs[0],
        end_idx=idxs[-1],
    )


def detect_box_sweep(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    box: VenomBox,
    i: int,
    *,
    pierce_frac: float = 0.0005,
) -> Optional[str]:
    """Return 'low' or 'high' if bar i sweeps box then closes back inside.

    Bullish sweep: low pierces below box.low, close back above box.low.
    Bearish sweep: high pierces above box.high, close back below box.high.
    """
    if i <= box.end_idx or i >= len(closes):
        return None
    h, l, c = float(highs[i]), float(lows[i]), float(closes[i])
    pad_lo = box.low * (1.0 - pierce_frac)
    pad_hi = box.high * (1.0 + pierce_frac)
    # Must be after box window (bar index after end_idx)
    if l < box.low and l <= pad_lo + (box.low - pad_lo) * 0.5 and c > box.low:
        return "low"
    if h > box.high and h >= pad_hi - (pad_hi - box.high) * 0.5 and c < box.high:
        return "high"
    # Softer: pierce and close inside box range
    if l < box.low and c >= box.low and c <= box.high:
        return "low"
    if h > box.high and c <= box.high and c >= box.low:
        return "high"
    return None


def collect_fvgs_in_range(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    start: int,
    end: int,
) -> List[FairValueGap]:
    out: List[FairValueGap] = []
    for i in range(max(start, 2), min(end + 1, len(closes))):
        g = detect_fvg_at(highs, lows, i, mid=float(closes[i]))
        if g:
            out.append(g)
    return out


def find_bpr(
    fvgs: Sequence[FairValueGap],
) -> Optional[BalancedPriceRange]:
    """First overlapping bullish+bearish FVG pair (by zone overlap)."""
    bulls = [g for g in fvgs if g.side == "bullish"]
    bears = [g for g in fvgs if g.side == "bearish"]
    best: Optional[BalancedPriceRange] = None
    best_w = 0.0
    for b in bulls:
        for e in bears:
            lo = max(b.gap_low, e.gap_low)
            hi = min(b.gap_high, e.gap_high)
            if hi > lo:
                w = hi - lo
                if w > best_w:
                    best_w = w
                    best = BalancedPriceRange(
                        low=lo,
                        high=hi,
                        bull_index=b.index,
                        bear_index=e.index,
                    )
    return best


def is_bullish_engulf(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    i: int,
) -> bool:
    if i < 1:
        return False
    o0, c0 = float(opens[i - 1]), float(closes[i - 1])
    o1, c1 = float(opens[i]), float(closes[i])
    return c0 < o0 and c1 > o1 and c1 >= o0 and o1 <= c0


def is_bearish_engulf(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    i: int,
) -> bool:
    if i < 1:
        return False
    o0, c0 = float(opens[i - 1]), float(closes[i - 1])
    o1, c1 = float(opens[i]), float(closes[i])
    return c0 > o0 and c1 < o1 and c1 <= o0 and o1 >= c0


def structure_shift_up(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    i: int,
    lookback: int = 8,
) -> bool:
    """Proxy MSS: close above recent swing high (prior lookback)."""
    if i < lookback + 1:
        return False
    swing = max(float(x) for x in highs[i - lookback : i])
    return float(closes[i]) > swing


def structure_shift_down(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    i: int,
    lookback: int = 8,
) -> bool:
    if i < lookback + 1:
        return False
    swing = min(float(x) for x in lows[i - lookback : i])
    return float(closes[i]) < swing


def _target_from_risk(entry: float, stop: float, side: str, r: float, box: VenomBox) -> float:
    risk = abs(entry - stop)
    if risk <= 0:
        risk = abs(box.high - box.low) * 0.25 or entry * 0.002
    if side == "CALL":
        t2r = entry + r * risk
        # Prefer at least box mid/high when close
        return max(t2r, box.mid)
    t2r = entry - r * risk
    return min(t2r, box.mid)


def scan_venom_signals(
    timestamps: Sequence,
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    session: date,
    *,
    r_multiple: float = 2.0,
    require_bpr: bool = False,
    require_structure: bool = True,
    max_entries: int = 1,
) -> List[VenomSignal]:
    """Find Venom signals for one session date (after box complete)."""
    box = compute_venom_box(timestamps, highs, lows, session)
    if box is None:
        return []

    signals: List[VenomSignal] = []
    sweep_side: Optional[str] = None  # low | high
    sweep_i = -1
    sweep_extreme = 0.0

    for i in range(box.end_idx + 1, len(closes)):
        et = _to_et(timestamps[i])
        if et.date() != session:
            break
        if et.time() >= SESSION_END:
            break
        if et.time() < RTH_OPEN and i <= box.end_idx:
            continue

        # Detect first sweep of the day
        if sweep_side is None:
            sw = detect_box_sweep(highs, lows, closes, box, i)
            if sw:
                sweep_side = sw
                sweep_i = i
                sweep_extreme = float(lows[i]) if sw == "low" else float(highs[i])
            continue

        # After sweep: look for confirmation + entry
        if i <= sweep_i:
            continue

        fvgs = collect_fvgs_in_range(highs, lows, closes, sweep_i, i)
        bpr = find_bpr(fvgs)
        if require_bpr and bpr is None:
            continue

        c = float(closes[i])
        h = float(highs[i])
        l = float(lows[i])
        o = float(opens[i]) if opens else c

        if sweep_side == "low":
            # Bullish Venom
            if require_structure and not structure_shift_up(highs, lows, closes, i):
                # soft: allow if strong bull FVG present
                bulls = [g for g in fvgs if g.side == "bullish"]
                if not bulls:
                    continue
            zone_lo, zone_hi = (bpr.low, bpr.high) if bpr else (0.0, 0.0)
            if bpr is None and fvgs:
                bulls = [g for g in fvgs if g.side == "bullish"]
                if bulls:
                    g = bulls[-1]
                    zone_lo, zone_hi = g.gap_low, g.gap_high
            entry_type = ""
            entry = 0.0
            # BPR / FVG retest: price trades into zone with bullish close
            if zone_hi > zone_lo and l <= zone_hi and h >= zone_lo and c >= o:
                entry_type = "bpr_retest" if bpr else "fvg_retest"
                entry = c
            elif is_bullish_engulf(opens, highs, lows, closes, i):
                entry_type = "venom_engulf"
                entry = c
            if not entry_type:
                continue
            stop = min(sweep_extreme, box.low) * 0.999
            if stop >= entry:
                stop = entry - max(box.height * 0.15, entry * 0.001)
            target = _target_from_risk(entry, stop, "CALL", r_multiple, box)
            # Cap target preference toward box high
            target = max(target, min(box.high, entry + abs(entry - stop) * r_multiple))
            signals.append(
                VenomSignal(
                    side="CALL",
                    entry_type=entry_type,
                    entry=round(entry, 4),
                    stop=round(stop, 4),
                    target=round(target, 4),
                    sweep_extreme=round(sweep_extreme, 4),
                    box_high=round(box.high, 4),
                    box_low=round(box.low, 4),
                    index=i,
                    r_multiple=r_multiple,
                    notes=[
                        f"sweep_low @{sweep_extreme:.2f}",
                        f"box {box.low:.2f}-{box.high:.2f}",
                        entry_type,
                    ],
                )
            )
            if len(signals) >= max_entries:
                break

        elif sweep_side == "high":
            if require_structure and not structure_shift_down(highs, lows, closes, i):
                bears = [g for g in fvgs if g.side == "bearish"]
                if not bears:
                    continue
            zone_lo, zone_hi = (bpr.low, bpr.high) if bpr else (0.0, 0.0)
            if bpr is None and fvgs:
                bears = [g for g in fvgs if g.side == "bearish"]
                if bears:
                    g = bears[-1]
                    zone_lo, zone_hi = g.gap_low, g.gap_high
            entry_type = ""
            entry = 0.0
            if zone_hi > zone_lo and l <= zone_hi and h >= zone_lo and c <= o:
                entry_type = "bpr_retest" if bpr else "fvg_retest"
                entry = c
            elif is_bearish_engulf(opens, highs, lows, closes, i):
                entry_type = "venom_engulf"
                entry = c
            if not entry_type:
                continue
            stop = max(sweep_extreme, box.high) * 1.001
            if stop <= entry:
                stop = entry + max(box.height * 0.15, entry * 0.001)
            target = _target_from_risk(entry, stop, "PUT", r_multiple, box)
            target = min(target, max(box.low, entry - abs(stop - entry) * r_multiple))
            signals.append(
                VenomSignal(
                    side="PUT",
                    entry_type=entry_type,
                    entry=round(entry, 4),
                    stop=round(stop, 4),
                    target=round(target, 4),
                    sweep_extreme=round(sweep_extreme, 4),
                    box_high=round(box.high, 4),
                    box_low=round(box.low, 4),
                    index=i,
                    r_multiple=r_multiple,
                    notes=[
                        f"sweep_high @{sweep_extreme:.2f}",
                        f"box {box.low:.2f}-{box.high:.2f}",
                        entry_type,
                    ],
                )
            )
            if len(signals) >= max_entries:
                break

    return signals
