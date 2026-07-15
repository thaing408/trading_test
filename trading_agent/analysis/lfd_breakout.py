"""Peter Brandt Last Full Day (LFD) + TechCharts Type 1–4 breakout framework.

Structure-first risk: stop/target from pattern geometry (LFD, breakout boundary,
negation, measured move) rather than hardcoded % of price. ATR is only a
buffer/floor helper when structure is incomplete.

References:
- Brandt: Last Full Day Low as initial protective stop after breakout
- TechCharts (Kibar): classify breakout quality Types 1–4 using LFD vs negation
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence


class BreakoutType(str, Enum):
    """Post-breakout path quality (TechCharts / Brandt LFD framework)."""

    TYPE_1_MOMENTUM = "type_1_momentum"
    TYPE_2_STANDARD_RETEST = "type_2_standard_retest"
    TYPE_3_DEEP_RETEST = "type_3_deep_retest"
    TYPE_4_FAILED = "type_4_failed"
    UNKNOWN = "unknown"


class RiskPolicy(str, Enum):
    """How to place the initial stop for auto-trade / edge package."""

    # Brandt: just beyond LFD — tight; cuts Type 3 winners
    LFD_TIGHT = "lfd_tight"
    # Pattern purist: stop at negation — allows Type 3 shakeouts, wider risk
    NEGATION_STRUCTURE = "negation_structure"
    # Hybrid: prefer LFD when R:R to target stays healthy; else structure
    HYBRID = "hybrid"


@dataclass(frozen=True)
class LastFullDay:
    """Last completed bar entirely inside the pattern before breakout."""

    index: int
    high: float
    low: float
    close: float
    open: float = 0.0

    @property
    def stop_long(self) -> float:
        """Initial long stop reference: just below LFD low."""
        return float(self.low)

    @property
    def stop_short(self) -> float:
        """Initial short stop reference: just above LFD high."""
        return float(self.high)


@dataclass(frozen=True)
class StructureLevels:
    """Classical pattern structure used for PT/SL (not % of price)."""

    direction: str  # bullish | bearish | long | short
    breakout_level: float
    lfd_level: float  # LFD low (long) or LFD high (short)
    negation_level: float
    measured_target: float
    pattern_height: float
    source: str  # ohlcv_lfd | technical_proxy | atr_fallback
    lfd: Optional[LastFullDay] = None
    notes: tuple[str, ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.lfd is not None:
            d["lfd"] = asdict(self.lfd)
        return d


@dataclass(frozen=True)
class StructureRiskPackage:
    """Executable risk package grounded in structure (+ optional grade size)."""

    entry_price: float
    stop_loss: float
    profit_target: float
    maximum_risk: float
    maximum_reward: float
    risk_reward: float
    direction: str
    structure: StructureLevels
    risk_policy: str
    geometry_source: str  # structure_lfd | structure_negation | hybrid | atr_blend
    stop_basis: str  # lfd | negation | support | resistance | atr
    target_basis: str  # measured_move | resistance | support | atr
    buffer_used: float
    notes: tuple[str, ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        d = {
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "profit_target": self.profit_target,
            "maximum_risk": self.maximum_risk,
            "maximum_reward": self.maximum_reward,
            "risk_reward": self.risk_reward,
            "direction": self.direction,
            "risk_policy": self.risk_policy,
            "geometry_source": self.geometry_source,
            "stop_basis": self.stop_basis,
            "target_basis": self.target_basis,
            "buffer_used": self.buffer_used,
            "notes": list(self.notes),
            "structure": self.structure.as_dict(),
        }
        return d


@dataclass
class BreakoutPathState:
    """Live or historical classification relative to LFD / negation."""

    breakout_type: BreakoutType
    lfd_intact: bool
    negation_intact: bool
    retested_breakout: bool
    message: str
    recommended_action: str
    severity: str = "info"  # info | medium | high | critical

    def as_dict(self) -> Dict[str, Any]:
        return {
            "breakout_type": self.breakout_type.value,
            "lfd_intact": self.lfd_intact,
            "negation_intact": self.negation_intact,
            "retested_breakout": self.retested_breakout,
            "message": self.message,
            "recommended_action": self.recommended_action,
            "severity": self.severity,
        }


def _is_long(direction: str) -> bool:
    d = (direction or "").strip().lower()
    return d in ("bullish", "long", "buy")


def _is_short(direction: str) -> bool:
    d = (direction or "").strip().lower()
    return d in ("bearish", "short", "sell")


def identify_last_full_day(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    breakout_level: float,
    direction: str,
    opens: Sequence[float] | None = None,
    breakout_index: int | None = None,
    epsilon: float = 0.0,
) -> Optional[LastFullDay]:
    """Find the last completed bar fully inside the pattern before breakout.

    Long breakout: bar entirely at/below breakout_level (high <= level + eps).
    Short breakout: bar entirely at/above breakout_level (low >= level - eps).
    """
    n = min(len(highs), len(lows), len(closes))
    if n < 2 or breakout_level <= 0:
        return None
    ops = list(opens) if opens and len(opens) >= n else [float(closes[0])] * n
    # Default: breakout is last bar
    bi = breakout_index if breakout_index is not None else n - 1
    bi = max(1, min(bi, n - 1))
    eps = float(epsilon) if epsilon > 0 else max(breakout_level * 1e-4, 1e-6)
    long = _is_long(direction)

    for i in range(bi - 1, -1, -1):
        h, l, c, o = float(highs[i]), float(lows[i]), float(closes[i]), float(ops[i])
        if long:
            inside = h <= breakout_level + eps
        else:
            inside = l >= breakout_level - eps
        if inside:
            return LastFullDay(index=i, high=h, low=l, close=c, open=o)
    return None


def pattern_height_from_window(
    highs: Sequence[float],
    lows: Sequence[float],
    *,
    end_index: int,
    lookback: int = 20,
) -> float:
    """Height of consolidation window ending at end_index (exclusive of breakout bar)."""
    if not highs or not lows:
        return 0.0
    end = max(0, min(end_index, len(highs)))
    start = max(0, end - lookback)
    if end <= start:
        return 0.0
    return max(0.0, float(max(highs[start:end])) - float(min(lows[start:end])))


def resolve_structure_from_ohlcv(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    direction: str,
    opens: Sequence[float] | None = None,
    lookback: int = 20,
) -> Optional[StructureLevels]:
    """Build structure from OHLCV using prior swing as breakout boundary + LFD."""
    n = min(len(highs), len(lows), len(closes))
    if n < 5:
        return None
    long = _is_long(direction)
    # Prior window excludes last bar (assumed breakout / entry bar)
    prior_h = [float(x) for x in highs[-lookback - 1 : -1]] or [float(highs[-2])]
    prior_l = [float(x) for x in lows[-lookback - 1 : -1]] or [float(lows[-2])]
    if long:
        breakout_level = max(prior_h)
    else:
        breakout_level = min(prior_l)
    lfd = identify_last_full_day(
        highs,
        lows,
        closes,
        breakout_level=breakout_level,
        direction=direction,
        opens=opens,
        breakout_index=n - 1,
    )
    height = pattern_height_from_window(highs, lows, end_index=n - 1, lookback=lookback)
    if height <= 0:
        height = abs(float(closes[-1]) - breakout_level) * 2 or float(closes[-1]) * 0.02

    if long:
        lfd_level = float(lfd.low) if lfd else float(min(prior_l))
        negation = float(min(prior_l))  # opposite side of box / structure
        # Negation should be at or below LFD; if LFD is the last inside bar, negation is pattern low
        if lfd and negation > lfd.low:
            negation = float(min(prior_l + [lfd.low]))
        measured = round(breakout_level + height, 2)
        notes = ("ohlcv breakout above prior high",)
    else:
        lfd_level = float(lfd.high) if lfd else float(max(prior_h))
        negation = float(max(prior_h))
        if lfd and negation < lfd.high:
            negation = float(max(prior_h + [lfd.high]))
        measured = round(breakout_level - height, 2)
        notes = ("ohlcv breakdown below prior low",)

    return StructureLevels(
        direction="bullish" if long else "bearish",
        breakout_level=round(float(breakout_level), 2),
        lfd_level=round(float(lfd_level), 2),
        negation_level=round(float(negation), 2),
        measured_target=measured,
        pattern_height=round(float(height), 2),
        source="ohlcv_lfd",
        lfd=lfd,
        notes=notes,
    )


def resolve_structure_from_technical(
    *,
    price: float,
    direction: str,
    support: float,
    resistance: float,
    atr: float,
    breakout_state: str = "none",
) -> StructureLevels:
    """Proxy structure when full OHLCV window is unavailable.

    Uses support/resistance as pattern bounds:
    - Long: breakout≈resistance, LFD≈max(support, entry-related), negation≈support
    - Short: breakout≈support, LFD≈min(resistance, ...), negation≈resistance
    Measured move ≈ pattern height projected from breakout.
    """
    long = _is_long(direction)
    atr_f = float(atr) if atr and atr > 0 else max(price * 0.015, 0.01)
    sup = float(support) if support and support > 0 else price - atr_f * 1.5
    res = float(resistance) if resistance and resistance > 0 else price + atr_f * 1.5
    # Ensure ordering
    if sup > res:
        sup, res = res, sup
    height = max(res - sup, atr_f)
    notes: List[str] = ["technical_proxy S/R structure"]

    if long:
        breakout = res if breakout_state == "breakout" or price >= res * 0.998 else max(res * 0.99, price)
        # LFD proxy: recent demand — support of the box (tighter than full negation if nested)
        lfd_level = sup
        # Prefer a slightly higher structural shelf when price is extended
        if price - atr_f > sup:
            lfd_level = max(sup, price - atr_f * 1.2)
            notes.append("LFD proxied as support / ATR shelf under entry")
        negation = sup
        measured = round(breakout + height, 2)
        # If still inside range, measured still uses box height from breakout
        if breakout_state != "breakout":
            notes.append("no confirmed breakout — structure is anticipatory")
    else:
        breakout = sup if breakout_state == "breakdown" or price <= sup * 1.002 else min(sup * 1.01, price)
        lfd_level = res
        if price + atr_f < res:
            lfd_level = min(res, price + atr_f * 1.2)
            notes.append("LFD proxied as resistance / ATR shelf above entry")
        negation = res
        measured = round(breakout - height, 2)
        if breakout_state != "breakdown":
            notes.append("no confirmed breakdown — structure is anticipatory")

    source = "technical_proxy"
    if not support or not resistance:
        source = "atr_fallback"
        notes.append("missing S/R — ATR used to seed structure")

    return StructureLevels(
        direction="bullish" if long else "bearish",
        breakout_level=round(float(breakout), 2),
        lfd_level=round(float(lfd_level), 2),
        negation_level=round(float(negation), 2),
        measured_target=round(float(measured), 2),
        pattern_height=round(float(height), 2),
        source=source,
        lfd=None,
        notes=tuple(notes),
    )


def _buffer(atr: float, price: float, mult: float = 0.1) -> float:
    """Small structural buffer (not a % stop) — tick/ATR cushion beyond LFD."""
    a = float(atr) if atr and atr > 0 else price * 0.01
    return max(price * 0.0005, a * mult)


def build_structure_risk_package(
    *,
    entry_price: float,
    direction: str,
    structure: StructureLevels,
    atr: float = 0.0,
    risk_policy: RiskPolicy | str = RiskPolicy.HYBRID,
    stop_atr_mult: float = 1.0,
    target_atr_mult: float = 1.5,
    size_multiplier: float = 1.0,
    min_risk_reward: float = 1.5,
    risk_unit_dollars: float | None = None,
) -> StructureRiskPackage:
    """Map structure → stop/target/risk dollars. Prefer LFD over % of price.

    Grade ATR mults only:
    - scale a small buffer beyond LFD
    - cap how far ATR fallback may wander when structure is incomplete
    - scale reward ambition on measured move (partial for low grades)
    """
    entry = float(entry_price)
    long = _is_long(direction)
    policy = RiskPolicy(str(risk_policy)) if not isinstance(risk_policy, RiskPolicy) else risk_policy
    atr_f = float(atr) if atr and atr > 0 else max(entry * 0.015, 0.01)
    buf = _buffer(atr_f, entry, mult=0.08 * max(0.5, float(stop_atr_mult)))
    notes: List[str] = list(structure.notes)

    lfd = float(structure.lfd_level)
    neg = float(structure.negation_level)
    brk = float(structure.breakout_level)
    measured = float(structure.measured_target)

    # --- stop candidates ---
    if long:
        lfd_stop = round(lfd - buf, 2)
        neg_stop = round(neg - buf, 2)
        # stop must be below entry
        if lfd_stop >= entry:
            lfd_stop = round(entry - max(buf, atr_f * 0.5), 2)
            notes.append("LFD was above entry — clamped under entry")
        if neg_stop >= entry:
            neg_stop = round(min(lfd_stop, entry - atr_f * 0.5), 2)
        atr_stop = round(entry - atr_f * float(stop_atr_mult), 2)
    else:
        lfd_stop = round(lfd + buf, 2)
        neg_stop = round(neg + buf, 2)
        if lfd_stop <= entry:
            lfd_stop = round(entry + max(buf, atr_f * 0.5), 2)
            notes.append("LFD was below entry — clamped above entry")
        if neg_stop <= entry:
            neg_stop = round(max(lfd_stop, entry + atr_f * 0.5), 2)
        atr_stop = round(entry + atr_f * float(stop_atr_mult), 2)

    # Policy selection
    stop_basis = "lfd"
    geometry_source = "structure_lfd"
    if policy == RiskPolicy.LFD_TIGHT:
        stop = lfd_stop
        stop_basis = "lfd"
        geometry_source = "structure_lfd"
    elif policy == RiskPolicy.NEGATION_STRUCTURE:
        stop = neg_stop
        stop_basis = "negation"
        geometry_source = "structure_negation"
        notes.append("Policy negation_structure — allows Type 3 deep re-tests")
    else:
        # Hybrid: LFD if R:R to measured still >= min; else widen toward negation
        stop = lfd_stop
        stop_basis = "lfd"
        geometry_source = "hybrid"
        risk_pts_lfd = abs(entry - lfd_stop)
        reward_pts = abs(measured - entry) if measured > 0 else 0.0
        rr_lfd = (reward_pts / risk_pts_lfd) if risk_pts_lfd > 0 else 0.0
        if rr_lfd + 1e-9 < min_risk_reward and abs(entry - neg_stop) > 0:
            # Measured move still needs room — prefer measured target stretch, keep LFD
            # unless LFD stop is nonsense (too tight / zero risk)
            if risk_pts_lfd < atr_f * 0.25:
                stop = neg_stop
                stop_basis = "negation"
                notes.append("Hybrid: LFD too tight vs ATR — using negation")
            else:
                notes.append(f"Hybrid: LFD R:R {rr_lfd:.2f}; keeping LFD, stretch target if needed")
        # If structure source was pure ATR fallback, blend
        if structure.source == "atr_fallback":
            stop = atr_stop
            stop_basis = "atr"
            geometry_source = "atr_blend"
            notes.append("ATR blend — incomplete structure")

    # --- target: measured move primary; grade scales ambition ---
    target_basis = "measured_move"
    if long:
        grade_target = round(entry + atr_f * float(target_atr_mult), 2)
        # Prefer measured if above entry; for lower grades take earlier partial of measured
        if measured > entry:
            span = measured - entry
            # C/B take less of measured; A+ allow full / slight extension
            frac = min(1.15, max(0.55, 0.45 + 0.35 * float(target_atr_mult)))
            struct_target = round(entry + span * frac, 2)
            # Use the more ambitious of structure and grade floor when A-tier
            if float(target_atr_mult) >= 2.0:
                profit_target = max(struct_target, grade_target)
            else:
                profit_target = min(struct_target, max(grade_target, entry + span * 0.55))
                # still prefer structure when it is defined
                if structure.source in ("ohlcv_lfd", "technical_proxy"):
                    profit_target = struct_target
            target_basis = "measured_move"
        else:
            profit_target = grade_target
            target_basis = "atr"
            notes.append("measured target invalid — ATR target")
        # Cap runaway targets for credit-style later handled by caller risk $
        if brk > 0 and profit_target < brk and structure.source != "atr_fallback":
            # Target should clear breakout for longs
            profit_target = max(profit_target, round(brk + structure.pattern_height * 0.5, 2))
    else:
        grade_target = round(entry - atr_f * float(target_atr_mult), 2)
        if measured < entry:
            span = entry - measured
            frac = min(1.15, max(0.55, 0.45 + 0.35 * float(target_atr_mult)))
            struct_target = round(entry - span * frac, 2)
            if float(target_atr_mult) >= 2.0:
                profit_target = min(struct_target, grade_target)
            else:
                profit_target = struct_target if structure.source in ("ohlcv_lfd", "technical_proxy") else grade_target
            target_basis = "measured_move"
        else:
            profit_target = grade_target
            target_basis = "atr"
            notes.append("measured target invalid — ATR target")

    # Coherence
    if long and not (stop < entry < profit_target):
        if stop >= entry:
            stop = round(entry - atr_f * max(0.5, stop_atr_mult), 2)
            stop_basis = "atr"
            notes.append("coherence fix: stop forced below entry")
        if profit_target <= entry:
            profit_target = round(entry + atr_f * max(1.0, target_atr_mult), 2)
            target_basis = "atr"
            notes.append("coherence fix: target forced above entry")
    if not long and not (profit_target < entry < stop):
        if stop <= entry:
            stop = round(entry + atr_f * max(0.5, stop_atr_mult), 2)
            stop_basis = "atr"
            notes.append("coherence fix: stop forced above entry")
        if profit_target >= entry:
            profit_target = round(entry - atr_f * max(1.0, target_atr_mult), 2)
            target_basis = "atr"
            notes.append("coherence fix: target forced below entry")

    risk_pts = abs(entry - stop)
    reward_pts = abs(profit_target - entry)
    rr = (reward_pts / risk_pts) if risk_pts > 0 else 0.0

    # Dollar risk: prefer geometric risk * size; caller may override with portfolio %
    unit = float(risk_unit_dollars) if risk_unit_dollars and risk_unit_dollars > 0 else risk_pts
    max_risk = round(unit * max(0.25, float(size_multiplier)), 2)
    max_reward = round(max_risk * max(rr, 1.0), 2) if max_risk > 0 else round(reward_pts, 2)

    return StructureRiskPackage(
        entry_price=round(entry, 2),
        stop_loss=round(stop, 2),
        profit_target=round(profit_target, 2),
        maximum_risk=max_risk,
        maximum_reward=max_reward,
        risk_reward=round(rr, 4),
        direction="Bullish" if long else "Bearish",
        structure=structure,
        risk_policy=policy.value,
        geometry_source=geometry_source,
        stop_basis=stop_basis,
        target_basis=target_basis,
        buffer_used=round(buf, 4),
        notes=tuple(notes),
    )


def structure_package_for_setup(
    *,
    price: float,
    direction: str,
    support: float = 0.0,
    resistance: float = 0.0,
    atr: float = 0.0,
    breakout_state: str = "none",
    highs: Sequence[float] | None = None,
    lows: Sequence[float] | None = None,
    closes: Sequence[float] | None = None,
    opens: Sequence[float] | None = None,
    risk_policy: RiskPolicy | str = RiskPolicy.HYBRID,
    stop_atr_mult: float = 1.0,
    target_atr_mult: float = 1.5,
    size_multiplier: float = 1.0,
    min_risk_reward: float = 1.5,
) -> StructureRiskPackage:
    """One-shot: OHLCV structure if available, else technical proxy → risk package."""
    structure: StructureLevels | None = None
    if highs is not None and lows is not None and closes is not None and len(closes) >= 5:
        structure = resolve_structure_from_ohlcv(
            highs,
            lows,
            closes,
            direction=direction,
            opens=opens,
        )
    if structure is None:
        structure = resolve_structure_from_technical(
            price=price,
            direction=direction,
            support=support,
            resistance=resistance,
            atr=atr,
            breakout_state=breakout_state,
        )
    # Risk unit in $ geometric points * 1 (ranker multiplies strategy style later)
    atr_f = float(atr) if atr and atr > 0 else max(price * 0.015, 0.01)
    risk_unit = max(price * 0.02, atr_f)
    return build_structure_risk_package(
        entry_price=price,
        direction=direction,
        structure=structure,
        atr=atr_f,
        risk_policy=risk_policy,
        stop_atr_mult=stop_atr_mult,
        target_atr_mult=target_atr_mult,
        size_multiplier=size_multiplier,
        min_risk_reward=min_risk_reward,
        risk_unit_dollars=risk_unit,
    )


def classify_breakout_path(
    *,
    direction: str,
    entry_price: float,
    breakout_level: float,
    lfd_level: float,
    negation_level: float,
    current_price: float,
    session_high: float | None = None,
    session_low: float | None = None,
    measured_target: float = 0.0,
    use_intraday_extremes: bool = True,
) -> BreakoutPathState:
    """Classify Type 1–4 from current path (intraday-aware).

    Type 1: no meaningful pullback; LFD never tested
    Type 2: re-test of breakout; LFD intact
    Type 3: LFD violated; negation intact
    Type 4: negation broken
    """
    long = _is_long(direction)
    price = float(current_price)
    entry = float(entry_price)
    brk = float(breakout_level)
    lfd = float(lfd_level)
    neg = float(negation_level)
    hi = float(session_high) if session_high is not None else price
    lo = float(session_low) if session_low is not None else price
    if not use_intraday_extremes:
        hi, lo = price, price

    eps = max(abs(entry) * 1e-4, 0.01)

    if long:
        lfd_broken = lo < lfd - eps
        neg_broken = lo < neg - eps or price < neg - eps
        retest = lo <= brk + eps and hi > brk
        no_pullback = lo >= brk - eps and price >= entry
        momentum = price >= entry and lo > lfd + eps and lo > brk - eps * 5
    else:
        lfd_broken = hi > lfd + eps
        neg_broken = hi > neg + eps or price > neg + eps
        retest = hi >= brk - eps and lo < brk
        no_pullback = hi <= brk + eps and price <= entry
        momentum = price <= entry and hi < lfd - eps and hi < brk + eps * 5

    if neg_broken:
        return BreakoutPathState(
            breakout_type=BreakoutType.TYPE_4_FAILED,
            lfd_intact=not lfd_broken,
            negation_intact=False,
            retested_breakout=retest,
            message="Type 4 failed breakout — pattern negation level broken",
            recommended_action="Exit; thesis invalid. Do not manage as same pattern trade",
            severity="critical",
        )
    if lfd_broken:
        return BreakoutPathState(
            breakout_type=BreakoutType.TYPE_3_DEEP_RETEST,
            lfd_intact=False,
            negation_intact=True,
            retested_breakout=True,
            message="Type 3 deep re-test — LFD violated; pattern negation still intact",
            recommended_action=(
                "If stop was LFD-tight, likely stopped. If negation policy, hold reduced "
                "risk only until reclaim of LFD/breakout; trail under structure"
            ),
            severity="high",
        )
    if retest and not lfd_broken:
        return BreakoutPathState(
            breakout_type=BreakoutType.TYPE_2_STANDARD_RETEST,
            lfd_intact=True,
            negation_intact=True,
            retested_breakout=True,
            message="Type 2 standard re-test — breakout level tested; LFD intact",
            recommended_action="Hold if re-test holds; keep LFD as invalidation for healthy thesis",
            severity="medium",
        )
    if momentum or no_pullback:
        tgt_note = ""
        if measured_target > 0:
            if long and price >= measured_target:
                tgt_note = " (at/through measured move)"
            if not long and price <= measured_target:
                tgt_note = " (at/through measured move)"
        return BreakoutPathState(
            breakout_type=BreakoutType.TYPE_1_MOMENTUM,
            lfd_intact=True,
            negation_intact=True,
            retested_breakout=False,
            message=f"Type 1 momentum breakout — no meaningful pullback to LFD{tgt_note}",
            recommended_action="Hold for measured objective; trail under structure / EMA; avoid early scalp exit",
            severity="info",
        )
    return BreakoutPathState(
        breakout_type=BreakoutType.UNKNOWN,
        lfd_intact=not lfd_broken,
        negation_intact=not neg_broken,
        retested_breakout=retest,
        message="Breakout path not yet classifiable",
        recommended_action="Monitor LFD and negation; manage per plan stop",
        severity="info",
    )


def trail_stop_from_structure(
    *,
    direction: str,
    entry_price: float,
    current_stop: float,
    current_price: float,
    breakout_level: float,
    lfd_level: float,
    negation_level: float,
    structure_shelf: float = 0.0,
    atr: float = 0.0,
) -> tuple[float, str]:
    """Advance stop using structure (not fixed %), only in trade's favor.

    Rules of thumb:
    - After Type 1 extension: trail to breakout (old resistance→support) then LFD
    - Never widen stop
    """
    long = _is_long(direction)
    price = float(current_price)
    stop = float(current_stop)
    buf = _buffer(atr, price, 0.1)
    candidates: List[tuple[float, str]] = []
    if long:
        if price > breakout_level * 1.01:
            candidates.append((breakout_level - buf, "trail_to_breakout_support"))
        if structure_shelf > 0 and structure_shelf < price:
            candidates.append((structure_shelf - buf, "trail_to_structure_shelf"))
        # Only tighten
        best = stop
        reason = "hold_stop"
        for lvl, r in candidates:
            if lvl > best and lvl < price:
                best, reason = lvl, r
        return round(best, 2), reason
    else:
        if price < breakout_level * 0.99:
            candidates.append((breakout_level + buf, "trail_to_breakout_resistance"))
        if structure_shelf > 0 and structure_shelf > price:
            candidates.append((structure_shelf + buf, "trail_to_structure_shelf"))
        best = stop
        reason = "hold_stop"
        for lvl, r in candidates:
            if (best <= 0 or lvl < best) and lvl > price:
                best, reason = lvl, r
        return round(best, 2), reason
