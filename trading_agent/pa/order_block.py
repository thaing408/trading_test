"""Order blocks — ICT-style and common SMC-style (mechanical approximations).

Two complementary rule sets (same impulse family, different zone geometry):

**ICT-style (`style="ict"`)**
  - Displacement = impulsive move that leaves a 3-candle FVG (inefficiency)
    and expands ≥ min_disp_atr × ATR
  - Bullish OB = last *down-close* candle before the displacement leg
  - Zone = candle **body** [min(o,c), max(o,c)] (refined / mean-threshold style)
  - Invalidation = full close through far side of the body
  - Breaker = violated OB that flips role after close-through

**SMC / retail YouTube-style (`style="smc"`)**
  - Displacement = N consecutive directional closes with range expansion
    (no FVG required)
  - Bullish OB = last *bearish* candle (or small base of opposite candles)
    before the impulse
  - Zone = full candle **range** [low, high] (or body if refine_smc_body)
  - Mitigation / breaker similar, but looser touch rules

Pure OHLCV — no I/O. Entry scoring uses rejection at zone + optional HTF.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from trading_agent.pa.fvg import detect_fvg


@dataclass
class OrderBlock:
    """Detected order block zone."""

    side: str  # bullish | bearish
    style: str  # ict | smc
    zone_low: float
    zone_high: float
    index: int  # OB candle index
    impulse_end: int  # last bar of displacement leg
    body_low: float = 0.0
    body_high: float = 0.0
    mitigated: bool = False
    invalidated: bool = False
    is_breaker: bool = False
    notes: List[str] = field(default_factory=list)

    @property
    def mid(self) -> float:
        return (self.zone_low + self.zone_high) / 2.0

    @property
    def height(self) -> float:
        return max(0.0, self.zone_high - self.zone_low)


@dataclass
class BreakerBlock:
    """Failed order block that flipped after close-through."""

    side: str  # bullish | bearish — *new* role after flip
    style: str
    zone_low: float
    zone_high: float
    origin_ob_index: int
    break_index: int
    notes: List[str] = field(default_factory=list)

    @property
    def mid(self) -> float:
        return (self.zone_low + self.zone_high) / 2.0


def _atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    end: int,
    period: int = 14,
) -> float:
    if end < 1:
        return max(1e-9, float(highs[end]) - float(lows[end]))
    start = max(1, end - period + 1)
    trs: List[float] = []
    for i in range(start, end + 1):
        h, l, pc = float(highs[i]), float(lows[i]), float(closes[i - 1])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return max(1e-9, sum(trs) / len(trs)) if trs else 1e-9


def _body(o: float, c: float) -> Tuple[float, float]:
    return (min(o, c), max(o, c))


def _is_bearish_candle(o: float, c: float) -> bool:
    return c < o


def _is_bullish_candle(o: float, c: float) -> bool:
    return c > o


def _impulse_range(
    highs: Sequence[float],
    lows: Sequence[float],
    start: int,
    end: int,
) -> float:
    if end < start:
        return 0.0
    return max(float(highs[i]) for i in range(start, end + 1)) - min(
        float(lows[i]) for i in range(start, end + 1)
    )


def detect_ict_order_block_at(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    i: int,
    *,
    min_disp_atr: float = 1.2,
    lookback_ob: int = 8,
    atr_period: int = 14,
) -> Optional[OrderBlock]:
    """ICT-style OB ending with displacement confirmed at bar ``i``.

    ``i`` is the last bar of the impulse (typically the bar that completes FVG).
    Returns the last opposite-body candle before the impulse as the OB.
    """
    n = len(closes)
    if i < 3 or i >= n:
        return None
    fvg = detect_fvg(opens, highs, lows, closes, i)
    if not fvg:
        return None
    fside, _, _ = fvg
    atr = _atr(highs, lows, closes, i, atr_period)

    # Impulse window = FVG 3-candle leg [i-2, i]
    impulse_start = i - 2
    disp = _impulse_range(highs, lows, impulse_start, i)
    if disp < min_disp_atr * atr:
        return None

    # OB = last opposing candle at or before the FVG origin (i-2)
    search_hi = i - 2  # inclusive
    search_lo = max(0, search_hi - lookback_ob)

    if fside == "bullish":
        ob_idx = None
        for j in range(search_hi, search_lo - 1, -1):
            if _is_bearish_candle(float(opens[j]), float(closes[j])):
                ob_idx = j
                break
        if ob_idx is None:
            return None
        o, c = float(opens[ob_idx]), float(closes[ob_idx])
        bl, bh = _body(o, c)
        if bh <= bl:
            return None
        return OrderBlock(
            side="bullish",
            style="ict",
            zone_low=bl,
            zone_high=bh,
            index=ob_idx,
            impulse_end=i,
            body_low=bl,
            body_high=bh,
            notes=["ict_body", "fvg_displacement", f"disp_atr={disp / atr:.2f}"],
        )

    if fside == "bearish":
        ob_idx = None
        for j in range(search_hi, search_lo - 1, -1):
            if _is_bullish_candle(float(opens[j]), float(closes[j])):
                ob_idx = j
                break
        if ob_idx is None:
            return None
        o, c = float(opens[ob_idx]), float(closes[ob_idx])
        bl, bh = _body(o, c)
        if bh <= bl:
            return None
        return OrderBlock(
            side="bearish",
            style="ict",
            zone_low=bl,
            zone_high=bh,
            index=ob_idx,
            impulse_end=i,
            body_low=bl,
            body_high=bh,
            notes=["ict_body", "fvg_displacement", f"disp_atr={disp / atr:.2f}"],
        )
    return None


def detect_smc_order_block_at(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    i: int,
    *,
    impulse_bars: int = 3,
    min_disp_atr: float = 1.5,
    min_body_ratio: float = 0.55,
    lookback_ob: int = 6,
    atr_period: int = 14,
    use_full_range: bool = True,
) -> Optional[OrderBlock]:
    """Common SMC/YouTube OB: last opposite candle before directional impulse.

    Displacement at ``i`` = last of ``impulse_bars`` consecutive closes in one
    direction with cumulative range ≥ min_disp_atr × ATR and strong bodies.
    """
    n = len(closes)
    if i < impulse_bars or i >= n:
        return None
    atr = _atr(highs, lows, closes, i, atr_period)
    start = i - impulse_bars + 1
    # Consecutive bullish or bearish closes
    bull_run = all(
        _is_bullish_candle(float(opens[j]), float(closes[j])) for j in range(start, i + 1)
    )
    bear_run = all(
        _is_bearish_candle(float(opens[j]), float(closes[j])) for j in range(start, i + 1)
    )
    if not bull_run and not bear_run:
        return None

    # Body strength on impulse
    body_ok = 0
    for j in range(start, i + 1):
        rng = float(highs[j]) - float(lows[j])
        if rng <= 0:
            continue
        body = abs(float(closes[j]) - float(opens[j]))
        if body / rng >= min_body_ratio:
            body_ok += 1
    if body_ok < max(1, impulse_bars - 1):
        return None

    disp = _impulse_range(highs, lows, start, i)
    if disp < min_disp_atr * atr:
        return None

    if bull_run:
        search_end = start
        search_start = max(0, search_end - lookback_ob)
        ob_idx = None
        for j in range(search_end - 1, search_start - 1, -1):
            if _is_bearish_candle(float(opens[j]), float(closes[j])):
                ob_idx = j
                break
        if ob_idx is None:
            return None
        o, c = float(opens[ob_idx]), float(closes[ob_idx])
        bl, bh = _body(o, c)
        zl = float(lows[ob_idx]) if use_full_range else bl
        zh = float(highs[ob_idx]) if use_full_range else bh
        if zh <= zl:
            return None
        return OrderBlock(
            side="bullish",
            style="smc",
            zone_low=zl,
            zone_high=zh,
            index=ob_idx,
            impulse_end=i,
            body_low=bl,
            body_high=bh,
            notes=[
                "smc_range" if use_full_range else "smc_body",
                f"impulse_bars={impulse_bars}",
                f"disp_atr={disp / atr:.2f}",
            ],
        )

    # bear_run
    search_end = start
    search_start = max(0, search_end - lookback_ob)
    ob_idx = None
    for j in range(search_end - 1, search_start - 1, -1):
        if _is_bullish_candle(float(opens[j]), float(closes[j])):
            ob_idx = j
            break
    if ob_idx is None:
        return None
    o, c = float(opens[ob_idx]), float(closes[ob_idx])
    bl, bh = _body(o, c)
    zl = float(lows[ob_idx]) if use_full_range else bl
    zh = float(highs[ob_idx]) if use_full_range else bh
    if zh <= zl:
        return None
    return OrderBlock(
        side="bearish",
        style="smc",
        zone_low=zl,
        zone_high=zh,
        index=ob_idx,
        impulse_end=i,
        body_low=bl,
        body_high=bh,
        notes=[
            "smc_range" if use_full_range else "smc_body",
            f"impulse_bars={impulse_bars}",
            f"disp_atr={disp / atr:.2f}",
        ],
    )


def update_ob_state(
    ob: OrderBlock,
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    from_bar: Optional[int] = None,
    to_bar: Optional[int] = None,
) -> OrderBlock:
    """Mark mitigation / invalidation / breaker from price after impulse."""
    n = len(closes)
    start = from_bar if from_bar is not None else ob.impulse_end + 1
    end = to_bar if to_bar is not None else n - 1
    start = max(start, ob.impulse_end + 1)
    if start >= n or end < start:
        return ob

    for j in range(start, min(end + 1, n)):
        h, l, c = float(highs[j]), float(lows[j]), float(closes[j])
        # mitigation = touch into zone
        if l <= ob.zone_high and h >= ob.zone_low:
            ob.mitigated = True
        if ob.side == "bullish":
            # invalidation: close below zone low
            if c < ob.zone_low:
                ob.invalidated = True
                ob.is_breaker = True
                ob.notes = list(ob.notes) + [f"breaker_at={j}"]
                break
        else:
            if c > ob.zone_high:
                ob.invalidated = True
                ob.is_breaker = True
                ob.notes = list(ob.notes) + [f"breaker_at={j}"]
                break
    return ob


def to_breaker(ob: OrderBlock, break_index: int) -> Optional[BreakerBlock]:
    """Flip violated OB: bullish OB failure → bearish breaker, and reverse."""
    if not ob.invalidated and not ob.is_breaker:
        return None
    new_side = "bearish" if ob.side == "bullish" else "bullish"
    return BreakerBlock(
        side=new_side,
        style=ob.style,
        zone_low=ob.zone_low,
        zone_high=ob.zone_high,
        origin_ob_index=ob.index,
        break_index=break_index,
        notes=[f"from_{ob.side}_ob", f"style={ob.style}"],
    )


def find_order_blocks(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    styles: Sequence[str] = ("ict", "smc"),
    lookback: int = 60,
    max_age_bars: int = 40,
    include_mitigated: bool = True,
    include_invalidated: bool = False,
) -> List[OrderBlock]:
    """Scan recent bars for ICT and/or SMC order blocks; update mitigation state."""
    n = len(closes)
    if n < 6:
        return []
    start = max(3, n - lookback)
    seen: set = set()  # (style, side, index)
    out: List[OrderBlock] = []

    for i in range(start, n):
        candidates: List[Optional[OrderBlock]] = []
        if "ict" in styles:
            candidates.append(
                detect_ict_order_block_at(opens, highs, lows, closes, i)
            )
        if "smc" in styles:
            candidates.append(
                detect_smc_order_block_at(opens, highs, lows, closes, i)
            )
        for raw in candidates:
            if raw is None:
                continue
            key = (raw.style, raw.side, raw.index)
            if key in seen:
                continue
            age = n - 1 - raw.impulse_end
            if age > max_age_bars:
                continue
            update_ob_state(raw, highs, lows, closes, from_bar=raw.impulse_end + 1, to_bar=n - 1)
            if raw.invalidated and not include_invalidated:
                continue
            if raw.mitigated and not include_mitigated and not include_invalidated:
                # still allow first mitigation as active zone when include_mitigated
                pass
            seen.add(key)
            out.append(raw)

    # Prefer fresher impulse_end
    out.sort(key=lambda x: (x.impulse_end, x.index))
    return out[-20:]


def find_active_order_blocks(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    styles: Sequence[str] = ("ict", "smc"),
    lookback: int = 60,
    max_age_bars: int = 40,
) -> List[OrderBlock]:
    """Un-invalidated OBs still valid as support/resistance (mitigated OK)."""
    blocks = find_order_blocks(
        opens,
        highs,
        lows,
        closes,
        styles=styles,
        lookback=lookback,
        max_age_bars=max_age_bars,
        include_mitigated=True,
        include_invalidated=False,
    )
    return [b for b in blocks if not b.invalidated]


def find_breakers(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    styles: Sequence[str] = ("ict", "smc"),
    lookback: int = 80,
    max_age_bars: int = 50,
) -> List[BreakerBlock]:
    """Order blocks that closed through and flipped."""
    blocks = find_order_blocks(
        opens,
        highs,
        lows,
        closes,
        styles=styles,
        lookback=lookback,
        max_age_bars=max_age_bars,
        include_mitigated=True,
        include_invalidated=True,
    )
    out: List[BreakerBlock] = []
    n = len(closes)
    for ob in blocks:
        if not ob.invalidated:
            continue
        # approximate break index from notes or scan
        brk_i = n - 1
        for note in ob.notes:
            if note.startswith("breaker_at="):
                try:
                    brk_i = int(note.split("=", 1)[1])
                except ValueError:
                    pass
        br = to_breaker(ob, brk_i)
        if br:
            out.append(br)
    return out[-12:]


def score_order_block_entry(
    highs: Sequence[float],
    lows: Sequence[float],
    opens: Sequence[float],
    closes: Sequence[float],
    *,
    htf_direction: str = "",
    styles: Sequence[str] = ("ict", "smc"),
    require_rejection: bool = True,
    r_multiple: float = 1.5,
) -> Tuple[bool, str, float, List[str], float, float, float]:
    """Score current bar for OB mitigation entry (both styles).

    Returns (play, side CALL|PUT|"", score, tags, entry, stop, target).
    ICT confluence with SMC same-side zone boosts score.
    """
    from trading_agent.pa.reactions import rejection_at_level

    n = len(closes)
    if n < 8:
        return False, "", 0.0, [], 0.0, 0.0, 0.0

    active = find_active_order_blocks(
        opens, highs, lows, closes, styles=styles, lookback=70, max_age_bars=45
    )
    breakers = find_breakers(
        opens, highs, lows, closes, styles=styles, lookback=80, max_age_bars=50
    )

    i = n - 1
    c = float(closes[i])
    h = float(highs[i])
    l = float(lows[i])
    o = float(opens[i]) if opens else float(closes[i - 1])
    tags: List[str] = []
    best: Optional[OrderBlock] = None
    best_score = 0.0
    side = ""
    used_breaker = False
    best_brk: Optional[BreakerBlock] = None

    # Group by side for ICT+SMC confluence
    by_side_styles: dict = {"bullish": set(), "bearish": set()}
    for ob in active:
        by_side_styles.setdefault(ob.side, set()).add(ob.style)

    for ob in reversed(active):
        touches = l <= ob.zone_high and h >= ob.zone_low
        if not touches:
            continue
        rej_side = "long" if ob.side == "bullish" else "short"
        rejected = rejection_at_level(h, l, o, c, ob.mid, side=rej_side)
        if require_rejection and not rejected:
            if ob.side == "bullish" and not (c > o and c >= ob.zone_low):
                continue
            if ob.side == "bearish" and not (c < o and c <= ob.zone_high):
                continue

        score = 52.0
        if ob.style == "ict":
            score += 10.0
            tags.append("ob_ict")
        else:
            score += 6.0
            tags.append("ob_smc")
        if rejected:
            score += 14.0
            tags.append("rejection")
        if ob.mitigated:
            score += 4.0  # first return narrative already happening
            tags.append("mitigating")
        # Dual-style confluence
        styles_here = by_side_styles.get(ob.side, set())
        if "ict" in styles_here and "smc" in styles_here:
            score += 12.0
            tags.append("ict+smc_confluence")
        # Prefer body mid for ICT
        if ob.style == "ict":
            score += 3.0

        aligned = True
        if htf_direction == "up" and ob.side != "bullish":
            aligned = False
        if htf_direction == "down" and ob.side != "bearish":
            aligned = False
        if htf_direction in ("up", "down"):
            if aligned:
                score += 10.0
                tags.append(f"htf_{htf_direction}")
            else:
                score -= 22.0
                tags.append("htf_against")

        tags.append(f"ob_{ob.side}")
        age = n - 1 - ob.impulse_end
        tags.append(f"age={age}")
        if score > best_score:
            best_score = score
            best = ob
            side = "CALL" if ob.side == "bullish" else "PUT"
            used_breaker = False

    # Breaker retest (secondary)
    for br in reversed(breakers):
        touches = l <= br.zone_high and h >= br.zone_low
        if not touches:
            continue
        rej_side = "long" if br.side == "bullish" else "short"
        rejected = rejection_at_level(h, l, o, c, br.mid, side=rej_side)
        if require_rejection and not rejected:
            if br.side == "bullish" and not (c > o):
                continue
            if br.side == "bearish" and not (c < o):
                continue
        score = 48.0 + (12.0 if rejected else 0.0)
        score += 8.0 if br.style == "ict" else 5.0
        if htf_direction == "up" and br.side == "bullish":
            score += 8.0
        if htf_direction == "down" and br.side == "bearish":
            score += 8.0
        if htf_direction == "up" and br.side == "bearish":
            score -= 18.0
        if htf_direction == "down" and br.side == "bullish":
            score -= 18.0
        if score > best_score:
            best_score = score
            best = None
            best_brk = br
            used_breaker = True
            side = "CALL" if br.side == "bullish" else "PUT"
            tags = [f"breaker_{br.side}", f"style={br.style}"]
            if rejected:
                tags.append("rejection")

    if best is None and not used_breaker:
        return False, "", 18.0, ["no_ob_touch"], 0.0, 0.0, 0.0

    entry = c
    if used_breaker and best_brk is not None:
        zone_low, zone_high = best_brk.zone_low, best_brk.zone_high
    else:
        assert best is not None
        zone_low, zone_high = best.zone_low, best.zone_high

    if side == "CALL":
        stop = zone_low * 0.998
        risk = entry - stop
        if risk <= 0:
            stop = entry * 0.995
            risk = entry - stop
        target = entry + risk * r_multiple
    else:
        stop = zone_high * 1.002
        risk = stop - entry
        if risk <= 0:
            stop = entry * 1.005
            risk = stop - entry
        target = entry - risk * r_multiple

    play = best_score >= 55.0 and side in ("CALL", "PUT")
    if htf_direction == "up" and side == "PUT":
        play = False
    if htf_direction == "down" and side == "CALL":
        play = False
    # de-dupe tags while preserving order
    seen_t = set()
    uniq_tags = []
    for t in tags:
        if t not in seen_t:
            seen_t.add(t)
            uniq_tags.append(t)
    return play, side, min(100.0, best_score), uniq_tags, entry, stop, target
