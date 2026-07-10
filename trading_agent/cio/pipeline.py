"""Orchestrate CIO final decision pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from trading_agent.cio.config import CIOConfig
from trading_agent.cio.decisions import process_all_candidates
from trading_agent.cio.loader import load_cio_inputs
from trading_agent.cio.models import CIOReport
from trading_agent.cio.portfolio import allocate_portfolio
from trading_agent.cio.reporter import render_cio_report


def run_cio_pipeline(config: CIOConfig) -> CIOReport:
    session_dir = Path(config.session_dir) if config.session_dir else None
    candidates, context = load_cio_inputs(
        config.fixture_mode,
        config.inputs_file,
        session_dir=session_dir,
        mode=config.cio_mode,
    )

    # Capital preservation: elevated uncertainty → full cash, no approvals
    if context.stay_in_cash and context.market_environment_score < 50:
        _, portfolio = allocate_portfolio([], context, config, rejected_count=len(candidates))
        return CIOReport(
            date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            context=context,
            approved=[],
            modified=[],
            rejected=[],
            portfolio=portfolio,
            governance_notes=[
                "Capital preservation is the highest priority",
                "Phase stay-in-cash + weak/suboptimal environment — no capital deployment",
                "Would a professional hedge fund approve? No — remain in cash",
            ],
            metadata={
                "source": "cio_pipeline",
                "candidates_reviewed": str(len(candidates)),
                "posture": "cash",
            },
        )

    approved_raw, modified_raw, rejected = process_all_candidates(candidates, context, config)
    book = approved_raw + modified_raw
    allocated, portfolio = allocate_portfolio(
        book,
        context,
        config,
        rejected_count=len(rejected),
        modified_count=len(modified_raw),
    )

    # Split allocated book back into pure approved vs modified for reporting
    approved = [t for t in allocated if t.decision == "Approve"]
    modified = [t for t in allocated if t.decision != "Approve"]
    # Trades dropped by concentration still count as rejected soft-drops? leave unallocated out
    allocated_tickers = {t.ticker for t in allocated}
    for t in book:
        if t.ticker not in allocated_tickers:
            from trading_agent.cio.models import RejectedDecision

            rejected.append(
                RejectedDecision(
                    ticker=t.ticker,
                    decision="Reject",
                    explanation="Dropped at portfolio construction — concentration/cash floors",
                    challenges=["Portfolio concentration or residual cash constraint"],
                    why_it_fails="Could not size without breaching sector/strategy/correlation caps",
                    thesis_invalidation="N/A — not allocated",
                    hedge_fund_approve="No — book construction veto",
                )
            )
    portfolio.rejected_count = len(rejected)
    portfolio.approved_count = len(approved)
    portfolio.modified_count = len(modified)

    governance = [
        "Capital preservation takes precedence over return maximization",
        "Every assumption challenged: regime, catalyst, technicals, sector, liquidity, correlation, size, R:R, POP, drawdown",
        "No FOMO-based approvals — institutional gate stack required",
        "Trades ranked by conviction score after cross-phase review",
    ]
    if context.market_environment_score < 55:
        governance.append("Elevated cash maintained due to suboptimal market environment")
    if not approved and not modified:
        governance.append("No candidates met institutional approval standards today — remain defensive")
    if portfolio.cash_allocation_pct >= 50:
        governance.append(
            f"Cash allocation {portfolio.cash_allocation_pct:.0f}% — uncertainty or selectivity elevated"
        )

    return CIOReport(
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        context=context,
        approved=approved,
        modified=modified,
        rejected=rejected,
        portfolio=portfolio,
        governance_notes=governance,
        metadata={
            "source": config.inputs_file or "fixture/cio_inputs.json",
            "candidates_reviewed": str(len(candidates)),
            "posture": "deploy" if (approved or modified) else "cash",
        },
    )


def render_report(config: CIOConfig) -> str:
    return render_cio_report(run_cio_pipeline(config))
