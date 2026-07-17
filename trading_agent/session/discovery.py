"""Intraday discovery refresh — light rescreen during RTH (Pacific schedule slots).

Morning research + CIO set the initial capital plan. Discovery re-runs research
at fixed PT slots, merges plan context, and **promotes to CIO** only when
tradeable ranked setups appear after a cash/empty morning — not every 15m cycle.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Sequence

from trading_agent.config import AgentConfig
from trading_agent.models import DailyTradingPlan, TradeOpportunity
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
    cio_promoted: bool = False
    cio_message: str = ""
    cio_approved: List[str] = field(default_factory=list)


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


def should_promote_to_cio(
    *,
    prior_stay_in_cash: bool,
    prior_ranked_count: int,
    prior_ranked_symbols: Sequence[str],
    new_plan: DailyTradingPlan,
) -> bool:
    """True when discovery found tradeable setups that morning CIO never saw.

    Does **not** fire on every scan: requires ≥1 ranked opportunity and either
    morning was cash/empty or the ranked set gained new symbols.
    """
    opps = list(new_plan.ranked_opportunities or [])
    if not opps or new_plan.stay_in_cash:
        return False
    if prior_stay_in_cash or prior_ranked_count <= 0:
        return True
    new_syms = {str(o.symbol).upper() for o in opps}
    old_syms = {str(s).upper() for s in prior_ranked_symbols}
    return bool(new_syms - old_syms)


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
    if result.cio_promoted:
        appr = ", ".join(result.cio_approved) if result.cio_approved else "none"
        lines.append(
            f"**CIO mid-session promotion:** re-evaluated capital on new tradeable "
            f"setups (approved: {appr}). Morning plan is no longer the sole capital gate."
        )
        if result.cio_message:
            lines.append(result.cio_message[:400])
    else:
        lines.append(
            "_Discovery does not re-run CIO every cycle — morning CIO capital plan "
            "governs size unless this refresh produces tradeable ranked setups "
            "(then CIO is promoted once). Watchlist alone is not approval._"
        )
    return "\n".join(lines)


def promote_discovery_to_cio(
    plan: DailyTradingPlan,
    *,
    session_dir: Path,
    fixture_mode: bool = False,
    portfolio_value: float = 100_000.0,
) -> dict:
    """Save CIO inputs from discovery plan and run approval pipeline once."""
    from trading_agent.cio.config import CIOConfig
    from trading_agent.cio.pipeline import run_cio_pipeline
    from trading_agent.session.cio_snapshot import save_cio_approval_snapshot
    from trading_agent.session.play_formatter import format_cio_plays

    save_cio_approval_snapshot(session_dir, plan, fixture_mode)
    cio_config = CIOConfig.from_env()
    cio_config.fixture_mode = fixture_mode
    cio_config.portfolio_value = portfolio_value
    cio_config.session_dir = str(session_dir)
    cio_config.cio_mode = "approval"
    report = run_cio_pipeline(cio_config)
    approved = [t.ticker for t in (report.approved or [])]
    message = format_cio_plays(report, title="CIO Discovery Promotion")
    # Persist promotion marker on session
    try:
        marker = session_dir / "cio_discovery_promotion.json"
        import json

        marker.write_text(
            json.dumps(
                {
                    "at": datetime.utcnow().isoformat() + "Z",
                    "opportunities": len(plan.ranked_opportunities or []),
                    "symbols": [o.symbol for o in (plan.ranked_opportunities or [])],
                    "approved": approved,
                    "stay_in_cash": plan.stay_in_cash,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass
    return {
        "approved": approved,
        "modified": [t.ticker for t in (report.modified or [])],
        "rejected_count": len(report.rejected or []),
        "message": message,
        "report": report,
    }


def run_discovery_refresh(
    agent_config: AgentConfig,
    *,
    session_dir: Path,
    prior_context: dict | None,
    slot_label: str,
    scheduled_at: datetime | None = None,
    promote_cio: bool = True,
    fixture_mode: bool = False,
    portfolio_value: float = 100_000.0,
    already_promoted: bool = False,
) -> DiscoveryRefreshResult:
    """Re-run research pipeline and merge into daily_plan_context.json.

    When ``promote_cio`` and tradeable ranked setups appear after a cash/empty
    morning (and we have not already promoted today), re-run CIO approval once.
    """
    prior = prior_context or {}
    prior_watch = [str(s) for s in (prior.get("top_watchlist") or [])]
    prior_ranked = [str(s) for s in (prior.get("ranked_symbols") or [])]
    prior_set = set(prior_watch) | set(prior_ranked)
    prior_stay = bool(prior.get("stay_in_cash", True))
    # ranked_opportunities may be list of dicts in saved context
    prior_ranked_count = 0
    prior_ranked_syms: List[str] = list(prior_ranked)
    raw_opps = prior.get("ranked_opportunities") or []
    if isinstance(raw_opps, list):
        prior_ranked_count = len(raw_opps)
        for o in raw_opps:
            if isinstance(o, dict) and o.get("symbol"):
                prior_ranked_syms.append(str(o["symbol"]))
            elif isinstance(o, TradeOpportunity):
                prior_ranked_syms.append(o.symbol)

    plan = run_pipeline(agent_config)
    ctx = plan_to_context(plan)
    ctx["discovery_refresh"] = {
        "slot": slot_label,
        "at": (scheduled_at or datetime.utcnow()).isoformat(),
        "prior_watchlist": prior_watch,
        "cio_promoted": False,
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

    cio_promoted = False
    cio_message = ""
    cio_approved: List[str] = []
    promote = (
        promote_cio
        and not already_promoted
        and should_promote_to_cio(
            prior_stay_in_cash=prior_stay,
            prior_ranked_count=prior_ranked_count,
            prior_ranked_symbols=prior_ranked_syms,
            new_plan=plan,
        )
    )
    if promote:
        try:
            promo = promote_discovery_to_cio(
                plan,
                session_dir=session_dir,
                fixture_mode=fixture_mode,
                portfolio_value=portfolio_value,
            )
            cio_promoted = True
            cio_approved = list(promo.get("approved") or [])
            cio_message = str(promo.get("message") or "")[:500]
            ctx["discovery_refresh"]["cio_promoted"] = True
            ctx["discovery_refresh"]["cio_approved"] = cio_approved
            # Clear stay-in-cash on plan context when CIO got real candidates
            # (plan itself may still flag cash if env weak — trust CIO report)
            if cio_approved:
                ctx["stay_in_cash"] = False
                ctx["cash_recommendation_reason"] = (
                    f"[discovery {slot_label}] CIO promoted — approved {', '.join(cio_approved)}"
                )
            save_plan_context(ctx, session_dir)
        except Exception as exc:  # noqa: BLE001
            cio_message = f"CIO promotion failed: {exc}"

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
        cio_promoted=cio_promoted,
        cio_message=cio_message,
        cio_approved=cio_approved,
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
