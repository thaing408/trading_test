"""Orchestrate intraday monitoring cycle."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from trading_agent.intraday.collectors.session import collect_session_snapshot
from trading_agent.intraday.config import IntradayConfig
from trading_agent.intraday.decisions.evaluator import evaluate_position
from trading_agent.intraday.models import Alert, IntradayReport, RiskLimitEvaluation
from trading_agent.intraday.plan_loader import load_plan_context, load_positions
from trading_agent.intraday.synthesis.session_context import synthesize_session


def _find_better_opportunity(plan_context: dict, positions: list) -> str | None:
    watchlist = plan_context.get("top_watchlist", [])
    held = {p.symbol for p in positions}
    for sym in watchlist:
        if sym not in held:
            return sym
    return None


def _evaluate_risk_limits(positions, snapshot, risk_config) -> RiskLimitEvaluation:
    breaches: List[str] = []
    total_risk = 0.0
    for pos in positions:
        sym = snapshot.symbols.get(pos.symbol)
        price = sym.price if sym else pos.current_price or pos.entry_price
        loss_pct = max(0, (pos.entry_price - price) / pos.entry_price * 100) if pos.entry_price else 0
        if loss_pct > risk_config.max_loss_per_position_pct:
            breaches.append(f"{pos.symbol}: loss {loss_pct:.1f}% > {risk_config.max_loss_per_position_pct}%")
        total_risk += loss_pct
    if total_risk > risk_config.max_portfolio_risk_pct:
        breaches.append(f"Portfolio aggregate risk {total_risk:.1f}% > {risk_config.max_portfolio_risk_pct}%")
    return RiskLimitEvaluation(within_limits=len(breaches) == 0, breaches=breaches)


def run_intraday_pipeline(config: IntradayConfig) -> IntradayReport:
    plan_context = load_plan_context(config.plan_file, config.fixture_mode)
    positions = load_positions(config.positions_file, config.fixture_mode)

    if not positions:
        snapshot = collect_session_snapshot(config, [], plan_context)
        synthesis = synthesize_session(snapshot)
        return IntradayReport(
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            cycle_count=config.cycles,
            session=synthesis,
            session_snapshot=snapshot,
            recommendations=[],
            notifications=[],
            risk_evaluation=RiskLimitEvaluation(within_limits=True),
            plan_context=plan_context,
            no_open_positions=True,
        )

    snapshot = collect_session_snapshot(config, positions, plan_context)
    synthesis = synthesize_session(snapshot)
    better_opp = _find_better_opportunity(plan_context, positions)

    recommendations = []
    all_notifications: List[Alert] = []
    for pos in positions:
        sym = snapshot.symbols.get(pos.symbol)
        if sym:
            pos.current_price = sym.price
        rec = evaluate_position(pos, snapshot, synthesis, config.risk, better_opp)
        recommendations.append(rec)
        all_notifications.extend(rec.alerts)

    risk_eval = _evaluate_risk_limits(positions, snapshot, config.risk)

    return IntradayReport(
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        cycle_count=config.cycles,
        session=synthesis,
        session_snapshot=snapshot,
        recommendations=recommendations,
        notifications=all_notifications,
        risk_evaluation=risk_eval,
        plan_context=plan_context,
        no_open_positions=False,
    )