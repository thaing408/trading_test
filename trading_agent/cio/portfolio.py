"""Portfolio construction and capital allocation."""

from __future__ import annotations

from collections import defaultdict
from typing import List, Tuple

from trading_agent.cio.config import CIOConfig
from trading_agent.cio.models import ApprovedTrade, PortfolioSummary, PhaseContext


def _risk_rating(confidence: float, rr: float) -> str:
    if confidence >= 70 and rr >= 2.5:
        return "Low"
    if confidence >= 55 and rr >= 2.0:
        return "Medium"
    return "High"


def apply_risk_rating(trade: ApprovedTrade, rr: float) -> ApprovedTrade:
    trade.risk_rating = _risk_rating(trade.confidence_score, rr)
    return trade


def allocate_portfolio(
    trades: List[ApprovedTrade],
    context: PhaseContext,
    config: CIOConfig,
    rejected_count: int = 0,
) -> Tuple[List[ApprovedTrade], PortfolioSummary]:
    if not trades:
        cash = 100.0 if context.stay_in_cash or context.market_environment_score < 45 else config.min_cash_pct + 50
        return [], PortfolioSummary(
            overall_market_bias=context.overall_market_bias,
            market_environment_score=context.market_environment_score,
            total_capital_recommended_pct=0.0,
            cash_allocation_pct=cash,
            approved_count=0,
            rejected_count=rejected_count,
            sector_allocation={},
            strategy_allocation={},
            average_probability=0.0,
            average_confidence=0.0,
            portfolio_risk_rating="Low",
        )

    scored = sorted(trades, key=lambda t: t.confidence_score, reverse=True)
    remaining_pct = 100.0 - config.min_cash_pct
    sector_used: dict[str, float] = defaultdict(float)
    strategy_used: dict[str, float] = defaultdict(float)
    allocated: list[ApprovedTrade] = []

    for trade in scored:
        base_pct = min(
            config.max_single_position_pct,
            max(5.0, trade.confidence_score / 100 * config.max_single_position_pct * 1.5),
        )
        if "Reduce size" in " ".join(trade.modifications):
            base_pct *= 0.75

        sector = trade.sector or "General"
        if sector_used[sector] + base_pct > config.max_sector_pct:
            base_pct = max(0, config.max_sector_pct - sector_used[sector])
        if strategy_used[trade.strategy] + base_pct > config.max_strategy_pct:
            base_pct = max(0, config.max_strategy_pct - strategy_used[trade.strategy])
        if base_pct < 2.0 or remaining_pct < base_pct:
            continue

        trade.position_size_pct = round(base_pct, 1)
        trade.dollar_allocation = round(config.portfolio_value * base_pct / 100, 2)
        sector_used[sector] += base_pct
        strategy_used[trade.strategy] += base_pct
        remaining_pct -= base_pct
        allocated.append(trade)

    total_pct = sum(t.position_size_pct for t in allocated)
    cash_pct = round(100.0 - total_pct, 1)
    avg_prob = sum(t.probability_of_success for t in allocated) / len(allocated) if allocated else 0
    avg_conf = sum(t.confidence_score for t in allocated) / len(allocated) if allocated else 0
    high_risk = sum(1 for t in allocated if t.risk_rating == "High")
    port_risk = "High" if high_risk > len(allocated) / 2 else "Medium" if high_risk else "Low"

    if context.market_environment_score < 50:
        cash_pct = max(cash_pct, 60.0)
        total_pct = 100.0 - cash_pct

    return allocated, PortfolioSummary(
        overall_market_bias=context.overall_market_bias,
        market_environment_score=context.market_environment_score,
        total_capital_recommended_pct=round(total_pct, 1),
        cash_allocation_pct=cash_pct,
        approved_count=len(allocated),
        rejected_count=rejected_count,
        sector_allocation={k: round(v, 1) for k, v in sector_used.items()},
        strategy_allocation={k: round(v, 1) for k, v in strategy_used.items()},
        average_probability=round(avg_prob, 2),
        average_confidence=round(avg_conf, 1),
        portfolio_risk_rating=port_risk,
    )