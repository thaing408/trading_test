"""Orchestrate CIO final decision pipeline."""

from __future__ import annotations

from datetime import datetime, timezone

from trading_agent.cio.config import CIOConfig
from trading_agent.cio.decisions import process_all_candidates
from trading_agent.cio.loader import load_cio_inputs
from trading_agent.cio.models import CIOReport
from trading_agent.cio.portfolio import allocate_portfolio
from trading_agent.cio.reporter import render_cio_report


def run_cio_pipeline(config: CIOConfig) -> CIOReport:
    candidates, context = load_cio_inputs(config.fixture_mode, config.inputs_file)

    if context.stay_in_cash and context.market_environment_score < 50:
        return CIOReport(
            date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            context=context,
            approved=[],
            rejected=[],
            portfolio=allocate_portfolio([], context, config)[1],
            governance_notes=[
                "Capital preservation priority: Phase 1 stay-in-cash signal with weak environment",
                "No trades forced — awaiting higher-quality setups",
            ],
            metadata={"source": "cio_pipeline", "candidates_reviewed": len(candidates)},
        )

    approved_raw, rejected = process_all_candidates(candidates, context, config)
    approved, portfolio = allocate_portfolio(approved_raw, context, config, len(rejected))
    portfolio.rejected_count = len(rejected)

    governance = [
        "Capital preservation takes precedence over return maximization",
        "All three phase outputs reviewed collectively before decision",
        "No FOMO-based approvals — evidence required for each gate",
    ]
    if context.market_environment_score < 55:
        governance.append("Elevated cash maintained due to suboptimal market environment")
    if not approved:
        governance.append("No candidates met institutional approval standards today")

    return CIOReport(
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        context=context,
        approved=approved,
        rejected=rejected,
        portfolio=portfolio,
        governance_notes=governance,
        metadata={
            "source": config.inputs_file or "fixture/cio_inputs.json",
            "candidates_reviewed": str(len(candidates)),
        },
    )


def render_report(config: CIOConfig) -> str:
    return render_cio_report(run_cio_pipeline(config))