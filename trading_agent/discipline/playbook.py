"""Bellafiore-style named playbook setups with hard checklist criteria.

Only catalogued plays that pass every required checklist item are eligible
for auto-trade ranking. Incomplete or unmatched names are non-tradeable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence


ChecklistFn = Callable[[Mapping[str, Any]], bool]


@dataclass(frozen=True)
class ChecklistItem:
    id: str
    description: str
    required: bool = True
    check: Optional[ChecklistFn] = None


@dataclass(frozen=True)
class PlaybookSetup:
    setup_id: str
    name: str
    direction: str  # Bullish | Bearish | Neutral
    strategy_names: tuple[str, ...]
    checklist: tuple[ChecklistItem, ...]
    min_grade: str = "B"
    notes: str = ""


@dataclass
class ChecklistResult:
    setup_id: str
    setup_name: str
    passed: bool
    items: List[Dict[str, Any]] = field(default_factory=list)
    failed_ids: List[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.passed:
            return f"{self.setup_name}: checklist PASS ({len(self.items)} items)"
        fails = ", ".join(self.failed_ids) or "unknown"
        return f"{self.setup_name}: checklist FAIL [{fails}]"


def _ctx_get(ctx: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for k in keys:
        if k in ctx and ctx[k] is not None:
            return ctx[k]
    return default


def _alignment(ctx: Mapping[str, Any]) -> str:
    return str(_ctx_get(ctx, "timeframe_alignment", "alignment", default="") or "").lower()


def _direction(ctx: Mapping[str, Any]) -> str:
    return str(_ctx_get(ctx, "direction", default="") or "").lower()


def _trend(ctx: Mapping[str, Any]) -> str:
    return str(_ctx_get(ctx, "trend", default="") or "").lower()


def _breakout(ctx: Mapping[str, Any]) -> str:
    return str(_ctx_get(ctx, "breakout_state", "breakout", default="") or "").lower()


def _rvol(ctx: Mapping[str, Any]) -> float:
    try:
        return float(_ctx_get(ctx, "relative_volume", "rvol", default=0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _rsi(ctx: Mapping[str, Any]) -> float:
    try:
        return float(_ctx_get(ctx, "rsi", default=50) or 50)
    except (TypeError, ValueError):
        return 50.0


def _adx(ctx: Mapping[str, Any]) -> float:
    try:
        return float(_ctx_get(ctx, "adx", default=0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _has_stop_target(ctx: Mapping[str, Any]) -> bool:
    try:
        stop = float(_ctx_get(ctx, "stop_loss", default=0) or 0)
        target = float(_ctx_get(ctx, "profit_target", default=0) or 0)
        entry = float(_ctx_get(ctx, "entry_price", "price", default=0) or 0)
    except (TypeError, ValueError):
        return False
    return stop > 0 and target > 0 and entry > 0 and stop != target


# --- Seed catalog (Bellafiore mechanism + small set of named plays) ---

PLAYBOOK_CATALOG: Dict[str, PlaybookSetup] = {
    "trend_pullback_long": PlaybookSetup(
        setup_id="trend_pullback_long",
        name="Trend Pullback Long",
        direction="Bullish",
        strategy_names=(
            "Long Call",
            "Bull Call Spread",
            "Debit Call Spread",
            "Cash Secured Put",
            "Covered Call",
            "Bull Put Credit Spread",
        ),
        min_grade="B",
        notes="Shannon HTF bullish + pullback entry; Douglas predefined stop/target",
        checklist=(
            ChecklistItem(
                "htf_bullish",
                "Higher-timeframe bias bullish or aligned_bullish",
                check=lambda c: _alignment(c) in ("aligned_bullish",)
                or _trend(c) in ("uptrend", "bullish"),
            ),
            ChecklistItem(
                "direction_long",
                "Trade direction is Bullish",
                check=lambda c: _direction(c) in ("bullish", "long", ""),
            ),
            ChecklistItem(
                "rvol_participation",
                "Relative volume >= 1.5x",
                check=lambda c: _rvol(c) >= 1.5,
            ),
            ChecklistItem(
                "not_overbought_extreme",
                "RSI not blow-off overbought (>98)",
                check=lambda c: _rsi(c) <= 98,
            ),
            ChecklistItem(
                "defined_risk",
                "Stop and target defined",
                check=_has_stop_target,
            ),
        ),
    ),
    "breakdown_momentum_short": PlaybookSetup(
        setup_id="breakdown_momentum_short",
        name="Breakdown Momentum Short",
        direction="Bearish",
        strategy_names=("Long Put", "Bear Put Spread", "Debit Put Spread", "Bear Call Credit Spread"),
        min_grade="B",
        notes="Confirmed breakdown with HTF bearish alignment",
        checklist=(
            ChecklistItem(
                "htf_bearish",
                "Higher-timeframe bias bearish or aligned_bearish",
                check=lambda c: _alignment(c) in ("aligned_bearish",)
                or _trend(c) in ("downtrend", "bearish"),
            ),
            ChecklistItem(
                "direction_short",
                "Trade direction is Bearish",
                check=lambda c: _direction(c) in ("bearish", "short"),
            ),
            ChecklistItem(
                "breakdown_confirm",
                "Breakout state is breakdown (or strong downtrend)",
                check=lambda c: _breakout(c) == "breakdown"
                or _trend(c) in ("downtrend", "bearish"),
            ),
            ChecklistItem(
                "rvol_participation",
                "Relative volume >= 1.5x",
                check=lambda c: _rvol(c) >= 1.5,
            ),
            ChecklistItem(
                "defined_risk",
                "Stop and target defined",
                check=_has_stop_target,
            ),
        ),
    ),
    "opening_range_breakout_long": PlaybookSetup(
        setup_id="opening_range_breakout_long",
        name="Opening Range Breakout Long",
        direction="Bullish",
        strategy_names=("Long Call", "Bull Call Spread", "Debit Call Spread"),
        min_grade="A",
        notes="Bellafiore ORB-style: breakout + volume + trend strength",
        checklist=(
            ChecklistItem(
                "breakout_confirm",
                "Breakout state is breakout",
                check=lambda c: _breakout(c) == "breakout",
            ),
            ChecklistItem(
                "aligned_or_up",
                "MTF aligned_bullish or uptrend",
                check=lambda c: _alignment(c) == "aligned_bullish"
                or _trend(c) in ("uptrend", "bullish"),
            ),
            ChecklistItem(
                "adx_strength",
                "ADX >= 18 (trend present)",
                check=lambda c: _adx(c) >= 18,
            ),
            ChecklistItem(
                "rvol_participation",
                "Relative volume >= 2.0x",
                check=lambda c: _rvol(c) >= 2.0,
            ),
            ChecklistItem(
                "defined_risk",
                "Stop and target defined",
                check=_has_stop_target,
            ),
        ),
    ),
    "mean_reversion_long": PlaybookSetup(
        setup_id="mean_reversion_long",
        name="Mean Reversion Long",
        direction="Bullish",
        strategy_names=("Long Call", "Bull Put Credit Spread", "Cash Secured Put"),
        min_grade="B",
        notes="Oversold bounce with defined risk (not against hard HTF conflict)",
        checklist=(
            ChecklistItem(
                "oversold",
                "RSI <= 35",
                check=lambda c: _rsi(c) <= 35,
            ),
            ChecklistItem(
                "not_hard_conflict",
                "Timeframes not conflicting",
                check=lambda c: _alignment(c) != "conflicting",
            ),
            ChecklistItem(
                "direction_long",
                "Trade direction is Bullish",
                check=lambda c: _direction(c) in ("bullish", "long", ""),
            ),
            ChecklistItem(
                "defined_risk",
                "Stop and target defined",
                check=_has_stop_target,
            ),
        ),
    ),
}


def get_setup(setup_id: str) -> PlaybookSetup | None:
    return PLAYBOOK_CATALOG.get(setup_id)


def list_setup_ids() -> List[str]:
    return sorted(PLAYBOOK_CATALOG.keys())


def evaluate_checklist(setup: PlaybookSetup, context: Mapping[str, Any]) -> ChecklistResult:
    items: List[Dict[str, Any]] = []
    failed: List[str] = []
    for item in setup.checklist:
        ok = True
        if item.check is not None:
            try:
                ok = bool(item.check(context))
            except Exception:
                ok = False
        items.append(
            {
                "id": item.id,
                "description": item.description,
                "required": item.required,
                "passed": ok,
            }
        )
        if item.required and not ok:
            failed.append(item.id)
    return ChecklistResult(
        setup_id=setup.setup_id,
        setup_name=setup.name,
        passed=len(failed) == 0,
        items=items,
        failed_ids=failed,
    )


def match_playbook(
    *,
    direction: str,
    strategy_name: str,
    context: Mapping[str, Any],
    preferred_setup_id: str | None = None,
) -> tuple[PlaybookSetup | None, ChecklistResult | None]:
    """Pick best matching catalog play for strategy/direction and evaluate checklist.

    If preferred_setup_id is set, only that play is tried.
    """
    d = (direction or "").lower()
    strat = strategy_name or ""
    candidates: List[PlaybookSetup] = []
    if preferred_setup_id:
        s = get_setup(preferred_setup_id)
        if s:
            candidates = [s]
    else:
        for s in PLAYBOOK_CATALOG.values():
            if s.direction.lower() == "neutral" or s.direction.lower() == d or not d:
                if not s.strategy_names or any(
                    sn.lower() in strat.lower() or strat.lower() in sn.lower()
                    for sn in s.strategy_names
                ):
                    candidates.append(s)
        # Fallback: direction-only match if strategy name didn't hit
        if not candidates:
            for s in PLAYBOOK_CATALOG.values():
                if s.direction.lower() == d:
                    candidates.append(s)

    best: tuple[PlaybookSetup, ChecklistResult] | None = None
    for setup in candidates:
        merged = dict(context)
        merged.setdefault("direction", direction)
        result = evaluate_checklist(setup, merged)
        if result.passed:
            return setup, result
        if best is None or len(result.failed_ids) < len(best[1].failed_ids):
            best = (setup, result)

    if best:
        return best[0], best[1]
    return None, None


def require_playbook_pass(
    *,
    direction: str,
    strategy_name: str,
    context: Mapping[str, Any],
    preferred_setup_id: str | None = None,
    require_named: bool = True,
) -> tuple[bool, str, str, ChecklistResult | None]:
    """Return (eligible, setup_id, reason, checklist)."""
    setup, result = match_playbook(
        direction=direction,
        strategy_name=strategy_name,
        context=context,
        preferred_setup_id=preferred_setup_id,
    )
    if setup is None or result is None:
        if require_named:
            return False, "", "No named playbook setup matched — not auto-trade eligible", None
        return True, "", "No playbook required", None
    if not result.passed:
        return (
            False,
            setup.setup_id,
            f"Playbook checklist failed: {result.summary}",
            result,
        )
    return True, setup.setup_id, result.summary, result
