"""Shannon multi-timeframe higher-bias gate.

Lower-timeframe signals against a defined higher-timeframe bias cannot ship
as A/A+. Conflicting alignment is forced non-tradeable (F) for auto-trade.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional


PRIORITY_GRADES = frozenset({"A+", "A"})


@dataclass(frozen=True)
class MtfGateResult:
    allowed: bool
    force_grade: Optional[str]
    reason: str
    higher_bias: str
    alignment: str


def higher_timeframe_bias(
    timeframe_trends: Mapping[str, str] | None,
    *,
    preferred_keys: tuple[str, ...] = ("weekly", "daily", "4h", "1h"),
) -> str:
    """Derive HTF bias from coarser frames first: bullish | bearish | neutral | unknown."""
    trends = timeframe_trends or {}
    for key in preferred_keys:
        val = str(trends.get(key, "") or "").lower()
        if not val or val in ("unavailable", "unknown", "mixed", "neutral", "none"):
            continue
        if val in ("uptrend", "bullish", "up"):
            return "bullish"
        if val in ("downtrend", "bearish", "down"):
            return "bearish"
    # Fallback: majority of remaining non-intraday keys
    bull = bear = 0
    for k, v in trends.items():
        if str(k).lower() in ("intraday", "1m", "5m", "15m"):
            continue
        vl = str(v or "").lower()
        if vl in ("uptrend", "bullish", "up"):
            bull += 1
        elif vl in ("downtrend", "bearish", "down"):
            bear += 1
    if bull > bear:
        return "bullish"
    if bear > bull:
        return "bearish"
    return "neutral" if (bull or bear) else "unknown"


def apply_mtf_gate(
    *,
    direction: str,
    timeframe_alignment: str,
    timeframe_trends: Mapping[str, str] | None = None,
    proposed_grade: str = "C",
) -> MtfGateResult:
    """Block or demote conflicting multi-TF for auto-trade eligibility.

    - alignment == conflicting → force F (not tradeable as A/A+/B/C for ship path)
    - trade direction against HTF bias → force F when grade would be A/A+; else demote note
    - aligned with HTF → allowed
    """
    align = (timeframe_alignment or "").lower().strip()
    d = (direction or "").lower().strip()
    htf = higher_timeframe_bias(timeframe_trends)

    if align == "conflicting":
        return MtfGateResult(
            allowed=False,
            force_grade="F",
            reason="Shannon gate: multi-timeframe conflicting — cannot ship as tradeable grade",
            higher_bias=htf,
            alignment=align,
        )

    if d in ("bullish", "long") and htf == "bearish":
        if proposed_grade in PRIORITY_GRADES or proposed_grade in ("B", "C"):
            return MtfGateResult(
                allowed=False,
                force_grade="F",
                reason="Shannon gate: long against higher-timeframe bearish bias",
                higher_bias=htf,
                alignment=align,
            )

    if d in ("bearish", "short") and htf == "bullish":
        if proposed_grade in PRIORITY_GRADES or proposed_grade in ("B", "C"):
            return MtfGateResult(
                allowed=False,
                force_grade="F",
                reason="Shannon gate: short against higher-timeframe bullish bias",
                higher_bias=htf,
                alignment=align,
            )

    # Soft: proposed A/A+ but alignment not explicitly aligned — demote to B ceiling
    if proposed_grade in PRIORITY_GRADES and align not in (
        "aligned_bullish",
        "aligned_bearish",
        "aligned",
    ):
        if align in ("mixed", "", "unknown"):
            return MtfGateResult(
                allowed=True,
                force_grade="B",
                reason="Shannon gate: A-tier requires clear HTF alignment — demoted to B",
                higher_bias=htf,
                alignment=align or "mixed",
            )

    return MtfGateResult(
        allowed=True,
        force_grade=None,
        reason=f"Shannon gate: OK (HTF={htf}, alignment={align or 'n/a'})",
        higher_bias=htf,
        alignment=align or "n/a",
    )


def is_a_tier_mtf_eligible(
    *,
    direction: str,
    timeframe_alignment: str,
    timeframe_trends: Mapping[str, str] | None = None,
) -> bool:
    gate = apply_mtf_gate(
        direction=direction,
        timeframe_alignment=timeframe_alignment,
        timeframe_trends=timeframe_trends,
        proposed_grade="A",
    )
    return gate.allowed and gate.force_grade is None
