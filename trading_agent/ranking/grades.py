"""Setup letter grades (A+/A/B/C/F) driving rank priority and PT/SL geometry.

Higher grades (A+/A) are always ranked ahead of B/C/F and use wider profit
targets / runner-style holds; lower grades take profit earlier with tighter stops.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple

from trading_agent.models import OptionsMetrics, ScreenerCandidate, TechnicalAnalysis

# Sort key: lower = better (A+ first)
GRADE_RANK = {"A+": 0, "A": 1, "B": 2, "C": 3, "F": 4}
GRADE_ORDER: Tuple[str, ...] = ("A+", "A", "B", "C", "F")

# ATR multipliers: (stop_atr, target_atr, hold_style, size_hint)
# Geometry tuned with offline backtest: keep A+ capital fully engaged; C at half size.
GRADE_TRADE_GEOMETRY = {
    "A+": (1.1, 2.8, "runner — trail under structure / EMA; allow full extension", 1.1),
    "A": (1.0, 2.0, "swing hold — full planned target before scale-out", 1.0),
    "B": (0.9, 1.5, "standard — take target; do not overstay", 0.75),
    "C": (0.75, 1.15, "early take-profit — scale out quickly; reduce ambition", 0.5),
    "F": (0.7, 1.0, "no new risk — reject / cash only", 0.0),
}


@dataclass(frozen=True)
class SetupGradeResult:
    grade: str
    grade_score: float
    reasons: List[str]
    stop_atr_mult: float
    target_atr_mult: float
    hold_style: str
    size_multiplier: float

    @property
    def is_tradeable(self) -> bool:
        return self.grade in ("A+", "A", "B", "C")

    @property
    def is_priority(self) -> bool:
        """A / A+ — take these first."""
        return self.grade in ("A+", "A")


def _pattern_bias(technical: TechnicalAnalysis) -> str:
    """Net bias from candle + PA signals: bullish | bearish | neutral."""
    bull = 0
    bear = 0
    for name in list(technical.candle_patterns or []) + list(technical.pa_signals or []):
        n = name.lower()
        if any(k in n for k in ("bullish", "hammer", "demand", "rs_flip_support", "qml_retest")):
            if "bearish" not in n:
                bull += 1
        if any(
            k in n
            for k in (
                "bearish",
                "shooting_star",
                "supply",
                "failed_breakout",
                "rs_flip_resistance",
            )
        ):
            bear += 1
        if n == "doji":
            pass
    if bull > bear:
        return "bullish"
    if bear > bull:
        return "bearish"
    return "neutral"


def compute_grade_score(
    technical: TechnicalAnalysis,
    options: OptionsMetrics,
    candidate: ScreenerCandidate,
    quality: float,
    confidence: float,
    direction: str = "Bullish",
) -> Tuple[float, List[str]]:
    """0–100 grade score starting from trade quality with structure/PA adjustments."""
    reasons: List[str] = []
    score = float(quality)
    reasons.append(f"Base quality {quality:.1f}")

    # Multi-timeframe alignment
    align = (technical.timeframe_alignment or "").lower()
    if align in ("aligned_bullish", "aligned_bearish"):
        score += 6
        reasons.append(f"Aligned multi-TF (+6): {technical.timeframe_alignment}")
    elif align == "conflicting":
        score -= 8
        reasons.append("Conflicting multi-TF (-8)")

    # Trend / MA stack
    if technical.ma_alignment == "bullish" and direction.lower() == "bullish":
        score += 3
        reasons.append("MA stack supports direction (+3)")
    elif technical.ma_alignment == "bearish" and direction.lower() == "bearish":
        score += 3
        reasons.append("MA stack supports direction (+3)")
    elif technical.ma_alignment in ("bullish", "bearish"):
        score -= 4
        reasons.append("MA stack conflicts with direction (-4)")

    # Breakout state
    if technical.breakout_state in ("breakout", "breakdown"):
        score += 3
        reasons.append(f"Confirmed {technical.breakout_state} (+3)")

    # Pattern alignment with trade direction
    pbias = _pattern_bias(technical)
    d = direction.lower()
    if pbias == "bullish" and d == "bullish":
        score += 5
        reasons.append(f"PA/candles support long (+5): {technical.pattern_summary}")
    elif pbias == "bearish" and d == "bearish":
        score += 5
        reasons.append(f"PA/candles support short (+5): {technical.pattern_summary}")
    elif pbias == "bearish" and d == "bullish":
        score -= 7
        reasons.append(f"PA/candles oppose long (-7): {technical.pattern_summary}")
    elif pbias == "bullish" and d == "bearish":
        score -= 7
        reasons.append(f"PA/candles oppose short (-7): {technical.pattern_summary}")
    elif technical.pattern_summary and technical.pattern_summary != "none":
        reasons.append(f"PA/candles neutral: {technical.pattern_summary}")

    # Liquidity / participation
    if candidate.relative_volume >= 2.0:
        score += 2
        reasons.append(f"RVOL {candidate.relative_volume:.1f}x (+2)")
    elif candidate.relative_volume < 1.2:
        score -= 3
        reasons.append(f"Soft RVOL {candidate.relative_volume:.1f}x (-3)")

    if candidate.institutional_score and candidate.institutional_score >= 70:
        score += 2
        reasons.append(f"Institutional score {candidate.institutional_score:.0f} (+2)")

    # Options friction
    if options.bid_ask_spread_pct and options.bid_ask_spread_pct > 3:
        score -= 4
        reasons.append(f"Wide options spread {options.bid_ask_spread_pct}% (-4)")
    if options.probability_of_profit and options.probability_of_profit < 0.5:
        score -= 3
        reasons.append(f"Low POP {options.probability_of_profit:.0%} (-3)")

    # Confidence floor nudge
    if confidence >= 80:
        score += 2
        reasons.append(f"High confidence {confidence:.0f} (+2)")
    elif confidence < 55:
        score -= 5
        reasons.append(f"Low confidence {confidence:.0f} (-5)")

    # Technical score soft floor
    if technical.score < 40:
        score -= 6
        reasons.append(f"Weak technical score {technical.score:.0f} (-6)")
    elif technical.score >= 70:
        score += 2
        reasons.append(f"Strong technical score {technical.score:.0f} (+2)")

    return round(min(100.0, max(0.0, score)), 1), reasons


def score_to_grade(grade_score: float) -> str:
    """Map grade_score to letter (example bands)."""
    if grade_score >= 85:
        return "A+"
    if grade_score >= 75:
        return "A"
    if grade_score >= 65:
        return "B"
    if grade_score >= 55:
        return "C"
    return "F"


def assign_setup_grade(
    technical: TechnicalAnalysis,
    options: OptionsMetrics,
    candidate: ScreenerCandidate,
    quality: float,
    confidence: float,
    direction: str = "Bullish",
    *,
    enforce_mtf_gate: bool = True,
) -> SetupGradeResult:
    grade_score, reasons = compute_grade_score(
        technical, options, candidate, quality, confidence, direction
    )
    grade = score_to_grade(grade_score)

    # Shannon higher-timeframe gate: conflicting / against HTF cannot ship A/A+
    if enforce_mtf_gate:
        from trading_agent.discipline.mtf_gate import apply_mtf_gate

        gate = apply_mtf_gate(
            direction=direction,
            timeframe_alignment=technical.timeframe_alignment or "",
            timeframe_trends=technical.timeframe_trends or {},
            proposed_grade=grade,
        )
        reasons.append(gate.reason)
        if gate.force_grade == "F":
            grade = "F"
            grade_score = min(grade_score, 49.0)
        elif gate.force_grade and GRADE_RANK.get(gate.force_grade, 99) > GRADE_RANK.get(
            grade, 99
        ):
            grade = gate.force_grade
            # Cap score into demoted band
            if grade == "B":
                grade_score = min(grade_score, 74.0)

    stop_m, target_m, hold, size_m = GRADE_TRADE_GEOMETRY[grade]
    reasons.append(f"Letter grade {grade} from score {grade_score:.1f}")
    reasons.append(
        f"Geometry: stop {stop_m}×ATR, target {target_m}×ATR — {hold}"
    )
    return SetupGradeResult(
        grade=grade,
        grade_score=grade_score,
        reasons=reasons,
        stop_atr_mult=stop_m,
        target_atr_mult=target_m,
        hold_style=hold,
        size_multiplier=size_m,
    )


def grade_sort_key(grade: str, grade_score: float, quality: float, confidence: float) -> Tuple:
    """Ascending sort key: A+ first, then higher scores."""
    return (
        GRADE_RANK.get(grade, 99),
        -grade_score,
        -quality,
        -confidence,
    )


def prefer_priority_grades(
    grades: Sequence[str],
    *,
    only_a_tier: bool = False,
) -> List[str]:
    """Filter helper: keep A+/A when present if only_a_tier."""
    if only_a_tier:
        return [g for g in grades if g in ("A+", "A")]
    return list(grades)
