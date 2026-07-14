"""Intraday discovery refresh — light rescreen during RTH (Pacific schedule slots).

Morning research + CIO remain the capital plan. Discovery re-runs the research
pipeline (expanded screener + ranking/book gates), merges into plan context,
and posts a short delta note. Not a full CIO rebuild every cycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from trading_agent.config import AgentConfig
from trading_agent.models import DailyTradingPlan
from trading_agent.pipeline import run_pipeline
from trading_agent.session.context import plan_to_context, save_plan_context


@dataclass
class DiscoveryRefreshResult:
    slot_label: str
    scheduled_at: str
    candidates_screened: int
    opportunities: int
    watchlist: List[str] = field(default_factory=list)
    new_symbols: List[str] = field(default_factory=list)
    dropped_symbols: List[str] = field(default_factory=list)
    stay_in_cash: bool = False
    cash_reason: str = ""
    plan: Optional[DailyTradingPlan] = None
    context: dict = field(default_factory=dict)
    prior_watchlist: List[str] = field(default_factory=list)


def _opp_lines(plan: DailyTradingPlan, limit: int = 5) -> List[str]:
    lines: List[str] = []
    for opp in plan.ranked_opportunities[:limit]:
        grade = getattr(opp, "setup_grade", "") or ""
        play = getattr(opp, "playbook_name", "") or getattr(opp, "playbook_setup_id", "") or ""
        lines.append(
            f"- **{opp.symbol}** {opp.strategy} grade={grade or 'n/a'} "
            f"conf={opp.confidence_score:.0f} "
            f"@ ${opp.entry_price:.2f} → PT ${opp.profit_target:.2f} / SL ${opp.stop_loss:.2f}"
            + (f" | {play}" if play else "")
        )
    return lines


def format_discovery_refresh(result: DiscoveryRefreshResult) -> str:
    lines = [
        f"**Discovery refresh** — {result.slot_label} ({result.scheduled_at})",
        f"Screened **{result.candidates_screened}** | Tradeable setups **{result.opportunities}**",
        "",
    ]
    if result.new_symbols:
        lines.append(f"**New on book/watch:** {', '.join(result.new_symbols)}")
    if result.dropped_symbols:
        lines.append(f"**No longer top-ranked:** {', '.join(result.dropped_symbols[:8])}")
    if not result.new_symbols and not result.dropped_symbols:
        lines.append("_Watchlist stable vs prior plan — no major rotation._")
    lines.append("")
    if result.plan and result.plan.ranked_opportunities:
        lines.append("**Ranked setups (refresh):**")
        lines.extend(_opp_lines(result.plan))
    elif result.stay_in_cash:
        lines.append(f"**Status:** stay in cash — {result.cash_reason[:200]}")
    else:
        lines.append("_No ranked opportunities this pass — keep morning plan risk rules._")
    lines.append("")
    lines.append(
        f"**Watchlist ({len(result.watchlist)}):** "
        + (", ".join(result.watchlist[:15]) if result.watchlist else "_empty_")
    )
    lines.append("")
    lines.append(
        "_Light discovery only — morning CIO capital plan still governs size; "
        "rails/cool-down still apply._"
    )
    return "\n".join(lines)


def run_discovery_refresh(
    agent_config: AgentConfig,
    *,
    session_dir: Path,
    prior_context: dict | None,
    slot_label: str,
    scheduled_at: datetime | None = None,
) -> DiscoveryRefreshResult:
    """Re-run research pipeline and merge into daily_plan_context.json."""
    prior = prior_context or {}
    prior_watch = [str(s) for s in (prior.get("top_watchlist") or [])]
    prior_ranked = [str(s) for s in (prior.get("ranked_symbols") or [])]
    prior_set = set(prior_watch) | set(prior_ranked)

    plan = run_pipeline(agent_config)
    ctx = plan_to_context(plan)
    ctx["discovery_refresh"] = {
        "slot": slot_label,
        "at": (scheduled_at or datetime.utcnow()).isoformat(),
        "prior_watchlist": prior_watch,
    }
    # Preserve morning cash reason if refresh also cash — annotate
    if plan.stay_in_cash and prior.get("cash_recommendation_reason"):
        ctx["cash_recommendation_reason"] = (
            f"[discovery {slot_label}] {plan.cash_recommendation_reason}"
        )
    save_plan_context(ctx, session_dir)

    # Refresh Mac-facing auto_trade_book on each discovery
    try:
        from trading_agent.export.auto_trade_book import export_plan_for_execution

        export_plan_for_execution(plan, session_dir=session_dir)
    except Exception:
        pass

    new_watch = list(plan.top_watchlist or [])
    new_ranked = [o.symbol for o in plan.ranked_opportunities]
    new_set = set(new_watch) | set(new_ranked)
    added = sorted(new_set - prior_set)
    dropped = sorted(prior_set - new_set)

    screened = int((plan.research_summary or {}).get("candidates_screened") or 0)

    return DiscoveryRefreshResult(
        slot_label=slot_label,
        scheduled_at=(
            scheduled_at.strftime("%Y-%m-%d %H:%M %Z")
            if scheduled_at
            else slot_label
        ),
        candidates_screened=screened,
        opportunities=len(plan.ranked_opportunities),
        watchlist=new_watch,
        new_symbols=added,
        dropped_symbols=dropped,
        stay_in_cash=plan.stay_in_cash,
        cash_reason=plan.cash_recommendation_reason or "",
        plan=plan,
        context=ctx,
        prior_watchlist=prior_watch,
    )


def due_discovery_slots(
    slots: tuple[datetime, ...] | list[datetime],
    *,
    now: datetime,
    already_run: set[str],
) -> List[datetime]:
    """Return discovery datetimes that are due and not yet completed (by HH:MM key)."""
    due: List[datetime] = []
    for slot in slots:
        key = slot.strftime("%H:%M")
        if key in already_run:
            continue
        # Compare in slot timezone
        n = now
        if n.tzinfo is None and slot.tzinfo is not None:
            n = n.replace(tzinfo=slot.tzinfo)
        elif n.tzinfo is not None and slot.tzinfo is not None:
            n = n.astimezone(slot.tzinfo)
        if n >= slot:
            due.append(slot)
    return due
