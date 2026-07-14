"""SMB top-ten trading books → auto-trade mechanisms.

Source list (SMB Capital blog, Bellafiore 2014):
https://www.smbtraining.com/blog/top-ten-trading-books

Already covered elsewhere in `discipline/`:
  4 Playbook (playbook.py), 6 Zone (edge.py), 8–9 Steenbarger (process.py)

This module adds pure gates for the remaining titles + a single entry point
used by `build_opportunities`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional, Sequence


# --- Catalog (for docs / process attribution; not marketing copy) ---

SMB_TOP_TEN: tuple[dict[str, str], ...] = (
    {
        "rank": "1",
        "title": "Reminiscences of a Stock Operator",
        "author": "Edwin Lefèvre",
        "mechanism": "livermore_tape_and_cut",
        "principle": "Follow the tape/trend; cut losses; never average a loser",
    },
    {
        "rank": "2",
        "title": "Market Wizards series",
        "author": "Jack Schwager",
        "mechanism": "wizards_risk_cap",
        "principle": "Hard risk cap; preserve capital; consistent unit risk",
    },
    {
        "rank": "3",
        "title": "How to Make Money in Stocks",
        "author": "William O'Neil",
        "mechanism": "oneil_can_slim_proxy",
        "principle": "RS + volume participation + breakout structure (CAN SLIM proxy)",
    },
    {
        "rank": "4",
        "title": "The PlayBook",
        "author": "Mike Bellafiore",
        "mechanism": "playbook_checklist",
        "principle": "Named setups with hard checklists (discipline/playbook.py)",
    },
    {
        "rank": "5",
        "title": "Markets in Profile",
        "author": "Jim Dalton",
        "mechanism": "dalton_value_area",
        "principle": "Price acceptance vs rejection vs value (profile proxy)",
    },
    {
        "rank": "6",
        "title": "Trading in the Zone",
        "author": "Mark Douglas",
        "mechanism": "edge_package",
        "principle": "Predefined edge + probabilistic discipline (discipline/edge.py)",
    },
    {
        "rank": "7",
        "title": "Trading to Win",
        "author": "Ari Kiev",
        "mechanism": "kiev_commitment",
        "principle": "Pre-committed daily loss halt; no freelancing mid-session",
    },
    {
        "rank": "8",
        "title": "Enhancing Trader Performance",
        "author": "Brett Steenbarger",
        "mechanism": "process_deliberate_practice",
        "principle": "Process score / deliberate practice metrics (process.py)",
    },
    {
        "rank": "9",
        "title": "The Psychology of Trading",
        "author": "Brett Steenbarger",
        "mechanism": "internal_observer",
        "principle": "Internal observer flags (revenge, FOMO, size-up)",
    },
    {
        "rank": "10",
        "title": "Thinking, Fast and Slow",
        "author": "Daniel Kahneman",
        "mechanism": "system2_gate",
        "principle": "System-2 veto of System-1 FOMO / overconfidence / loss-chase",
    },
)


@dataclass
class BookGateResult:
    ok: bool
    book: str
    mechanism: str
    reasons: List[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.ok:
            return f"{self.book}: OK"
        return f"{self.book}: BLOCK — " + "; ".join(self.reasons)


@dataclass
class SmbGatesResult:
    ok: bool
    results: List[BookGateResult] = field(default_factory=list)
    blocked_by: List[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.ok:
            return "SMB book gates: all passed"
        return "SMB book gates blocked: " + "; ".join(self.blocked_by)


def _f(ctx: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(ctx.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _s(ctx: Mapping[str, Any], key: str, default: str = "") -> str:
    return str(ctx.get(key, default) or default).lower().strip()


# --- 1 Lefèvre / Livermore ---


def livermore_tape_and_cut(ctx: Mapping[str, Any]) -> BookGateResult:
    """Follow tape (trend); refuse averaging a loser; directional alignment."""
    reasons: List[str] = []
    direction = _s(ctx, "direction")
    trend = _s(ctx, "trend")
    # Tape / trend alignment
    if direction in ("bullish", "long") and trend in ("downtrend", "bearish"):
        reasons.append("Livermore: long against tape/trend (downtrend)")
    if direction in ("bearish", "short") and trend in ("uptrend", "bullish"):
        reasons.append("Livermore: short against tape/trend (uptrend)")
    # Never average a loser on auto-trade path
    if ctx.get("averaging_down_loser") or ctx.get("add_to_loser"):
        reasons.append("Livermore: never average a losing position")
    # Cut losses: stop must be defined (edge also checks; belt-and-suspenders)
    if _f(ctx, "stop_loss") <= 0:
        reasons.append("Livermore: no cut-loss stop defined")
    return BookGateResult(
        ok=len(reasons) == 0,
        book="Reminiscences (Livermore)",
        mechanism="livermore_tape_and_cut",
        reasons=reasons,
    )


# --- 2 Schwager Market Wizards ---


def wizards_risk_cap(ctx: Mapping[str, Any], *, max_risk_per_trade_pct: float = 2.0) -> BookGateResult:
    """Hard unit risk; reject freelanced oversize."""
    reasons: List[str] = []
    proposed = _f(ctx, "proposed_risk_pct", _f(ctx, "maximum_risk_pct"))
    if proposed <= 0:
        reasons.append("Wizards: proposed risk pct missing")
    elif proposed > max_risk_per_trade_pct + 1e-9:
        reasons.append(
            f"Wizards: risk {proposed:.2f}% exceeds hard cap {max_risk_per_trade_pct:.2f}%"
        )
    if ctx.get("feeling_size_boost") or ctx.get("discretionary_size_up"):
        reasons.append("Wizards: size must be predefined, not discretionary mid-trade")
    if ctx.get("daily_loss_halt"):
        reasons.append("Wizards: daily loss halt active — capital preservation first")
    return BookGateResult(
        ok=len(reasons) == 0,
        book="Market Wizards (Schwager)",
        mechanism="wizards_risk_cap",
        reasons=reasons,
    )


# --- 3 O'Neil CAN SLIM proxy ---


def oneil_can_slim_proxy(
    ctx: Mapping[str, Any],
    *,
    min_rvol: float = 1.5,
    min_rs: float = 0.0,
    require_breakout_for_momentum: bool = True,
) -> BookGateResult:
    """Relative strength + volume + structure (proxy, not full CAN SLIM fundamentals)."""
    reasons: List[str] = []
    rvol = _f(ctx, "relative_volume", _f(ctx, "rvol"))
    rs = _f(ctx, "relative_strength", 1.0)
    breakout = _s(ctx, "breakout_state")
    setup = _s(ctx, "setup_id") or _s(ctx, "playbook_setup_id")
    direction = _s(ctx, "direction")

    if rvol < min_rvol:
        reasons.append(f"O'Neil: RVOL {rvol:.2f}x < {min_rvol}x (participation)")
    if min_rs > 0 and rs < min_rs and direction in ("bullish", "long"):
        reasons.append(f"O'Neil: relative strength {rs:.2f} below floor {min_rs:.2f}")

    # Momentum / ORB-style names need breakout confirmation
    momentumish = "breakout" in setup or "breakdown" in setup or breakout in (
        "breakout",
        "breakdown",
    )
    if require_breakout_for_momentum and "opening_range" in setup and breakout not in (
        "breakout",
        "breakdown",
    ):
        reasons.append("O'Neil: ORB-style play needs breakout/breakdown confirmation")
    if momentumish and direction in ("bullish", "long") and breakout == "breakdown":
        reasons.append("O'Neil: long momentum vs breakdown structure")
    if momentumish and direction in ("bearish", "short") and breakout == "breakout":
        reasons.append("O'Neil: short momentum vs breakout structure")

    return BookGateResult(
        ok=len(reasons) == 0,
        book="How to Make Money in Stocks (O'Neil)",
        mechanism="oneil_can_slim_proxy",
        reasons=reasons,
    )


# --- 5 Dalton Markets in Profile ---


def dalton_value_area(ctx: Mapping[str, Any]) -> BookGateResult:
    """Price acceptance vs rejection (simplified value-area proxy).

    Context keys (optional): session_high, session_low, price, setup_id.
    Value = middle 70% of session range. Breakout plays should reject from value
    (trade outside); mean-reversion should be at extremes reverting toward value.
    """
    reasons: List[str] = []
    hi = _f(ctx, "session_high", _f(ctx, "resistance"))
    lo = _f(ctx, "session_low", _f(ctx, "support"))
    px = _f(ctx, "price", _f(ctx, "entry_price"))
    setup = _s(ctx, "setup_id") or _s(ctx, "playbook_setup_id")
    if hi <= lo or px <= 0:
        # No session range — pass (gate inactive without data)
        return BookGateResult(
            ok=True,
            book="Markets in Profile (Dalton)",
            mechanism="dalton_value_area",
            reasons=["Dalton: value-area inactive (no session range)"],
        )

    span = hi - lo
    val_lo = lo + 0.15 * span
    val_hi = hi - 0.15 * span
    in_value = val_lo <= px <= val_hi
    above_value = px > val_hi
    below_value = px < val_lo

    if "mean_reversion" in setup:
        if in_value:
            reasons.append("Dalton: mean-reversion inside value — wait for extreme/rejection")
    elif "breakout" in setup or "breakdown" in setup or "opening_range" in setup:
        if in_value:
            reasons.append("Dalton: momentum play still inside value — no acceptance/break")
    elif "pullback" in setup:
        # Pullbacks preferred in/near value after trend acceptance
        if below_value and _s(ctx, "direction") in ("bullish", "long"):
            reasons.append("Dalton: long pullback below value (excess) — elevated risk")
        if above_value and _s(ctx, "direction") in ("bearish", "short"):
            reasons.append("Dalton: short pullback above value (excess) — elevated risk")

    return BookGateResult(
        ok=len(reasons) == 0,
        book="Markets in Profile (Dalton)",
        mechanism="dalton_value_area",
        reasons=reasons,
    )


# --- 7 Kiev Trading to Win ---


def kiev_commitment(ctx: Mapping[str, Any]) -> BookGateResult:
    """Pre-committed plan only; daily loss halt; no mid-session freelancing."""
    reasons: List[str] = []
    if ctx.get("daily_loss_halt") or ctx.get("max_daily_loss_hit"):
        reasons.append("Kiev: daily loss commitment hit — stop trading")
    if ctx.get("freelance_unplanned") or ctx.get("off_plan_entry"):
        reasons.append("Kiev: off-plan freelanced entry blocked")
    if ctx.get("checklist_passed") is False:
        reasons.append("Kiev: no commitment without passed checklist")
    return BookGateResult(
        ok=len(reasons) == 0,
        book="Trading to Win (Kiev)",
        mechanism="kiev_commitment",
        reasons=reasons,
    )


# --- 9–10 Steenbarger observer + Kahneman System 2 ---


def system2_and_observer(ctx: Mapping[str, Any]) -> BookGateResult:
    """System-2 veto: FOMO chase, revenge, overconfidence after win streak."""
    reasons: List[str] = []
    # FOMO: chase extension without volume
    if ctx.get("fomo_chase") or (
        _s(ctx, "breakout_state") == "breakout"
        and _f(ctx, "relative_volume") < 1.2
        and _s(ctx, "setup_id").find("breakout") >= 0
    ):
        if _f(ctx, "relative_volume") < 1.2:
            reasons.append("Kahneman/S2: FOMO breakout without volume participation")
    if ctx.get("revenge_reentry") or ctx.get("revenge_trade"):
        reasons.append("Observer/S2: revenge re-entry blocked")
    win_streak = int(_f(ctx, "win_streak", 0))
    if win_streak >= 3 and (
        ctx.get("size_up_after_wins") or _f(ctx, "proposed_risk_pct") > _f(ctx, "base_risk_pct", 2.0)
    ):
        reasons.append("Kahneman/S2: overconfidence size-up after win streak")
    if ctx.get("tilt") or ctx.get("emotional_override"):
        reasons.append("Observer: tilt/emotional override — invoke internal observer, stand down")
    return BookGateResult(
        ok=len(reasons) == 0,
        book="Steenbarger observer + Kahneman S2",
        mechanism="system2_and_observer",
        reasons=reasons,
    )


def apply_smb_book_gates(
    ctx: Mapping[str, Any],
    *,
    max_risk_per_trade_pct: float = 2.0,
    min_rvol: float = 1.5,
    min_rs: float = 0.0,
    enabled: bool = True,
) -> SmbGatesResult:
    """Run all SMB-derived gates (except Playbook/Zone/MTF handled elsewhere)."""
    if not enabled:
        return SmbGatesResult(ok=True, results=[], blocked_by=[])

    results = [
        livermore_tape_and_cut(ctx),
        wizards_risk_cap(ctx, max_risk_per_trade_pct=max_risk_per_trade_pct),
        oneil_can_slim_proxy(ctx, min_rvol=min_rvol, min_rs=min_rs),
        dalton_value_area(ctx),
        kiev_commitment(ctx),
        system2_and_observer(ctx),
    ]
    blocked = [r.summary for r in results if not r.ok]
    return SmbGatesResult(ok=len(blocked) == 0, results=results, blocked_by=blocked)


def smb_process_habit_lines() -> List[str]:
    """Steenbarger Enhancing Trader Performance — deliberate practice prompts."""
    return [
        "Deliberate practice (Steenbarger): tag every trade with setup_id + checklist_passed "
        "before reviewing P/L",
        "Internal observer (Psychology of Trading): journal FOMO/revenge/tilt flags same day",
        "System-2 (Kahneman): if emotional override fires, reduce size to zero until checklist re-pass",
    ]
