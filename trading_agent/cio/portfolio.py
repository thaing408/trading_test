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
    modified_count: int = 0,
) -> Tuple[List[ApprovedTrade], PortfolioSummary]:
    if not trades:
        cash = 100.0 if context.stay_in_cash or context.market_environment_score < 45 else min(
            100.0, config.min_cash_pct + 50
        )
        return [], PortfolioSummary(
            overall_market_bias=context.overall_market_bias,
            market_environment_score=context.market_environment_score,
            total_capital_recommended_pct=0.0,
            cash_allocation_pct=cash,
            approved_count=0,
            rejected_count=rejected_count,
            modified_count=modified_count,
            sector_allocation={},
            strategy_allocation={},
            average_probability=0.0,
            average_confidence=0.0,
            portfolio_risk_rating="Low",
            overall_portfolio_risk="Low — cash heavy",
            capital_efficiency_score=0.0,
            estimated_portfolio_drawdown_pct=0.0,
            correlation_note="No risk capital deployed",
        )

    # Conviction order for sizing priority
    scored = sorted(trades, key=lambda t: (t.conviction_score, t.confidence_score), reverse=True)
    remaining_pct = 100.0 - config.min_cash_pct
    sector_used: dict[str, float] = defaultdict(float)
    strategy_used: dict[str, float] = defaultdict(float)
    corr_used: dict[str, float] = defaultdict(float)
    allocated: list[ApprovedTrade] = []

    for trade in scored:
        base_pct = min(
            config.max_single_position_pct,
            max(5.0, trade.conviction_score / 100 * config.max_single_position_pct * 1.5),
        )
        mods_text = " ".join(trade.modifications)
        if "Reduce size 25%" in mods_text or "Reduce size" in mods_text:
            base_pct *= 0.75
        if "Size cut 30%" in mods_text:
            base_pct *= 0.70
        if "Reduce size 20%" in mods_text:
            base_pct *= 0.80

        sector = trade.sector or "General"
        corr = trade.correlation_group or sector
        if sector_used[sector] + base_pct > config.max_sector_pct:
            base_pct = max(0, config.max_sector_pct - sector_used[sector])
        if strategy_used[trade.strategy] + base_pct > config.max_strategy_pct:
            base_pct = max(0, config.max_strategy_pct - strategy_used[trade.strategy])
        # Soft correlation cluster cap (same as sector max)
        if corr_used[corr] + base_pct > config.max_sector_pct:
            base_pct = max(0, config.max_sector_pct - corr_used[corr])
        if base_pct < 2.0 or remaining_pct < base_pct:
            continue

        trade.position_size_pct = round(base_pct, 1)
        trade.dollar_allocation = round(config.portfolio_value * base_pct / 100, 2)
        sector_used[sector] += base_pct
        strategy_used[trade.strategy] += base_pct
        corr_used[corr] += base_pct
        remaining_pct -= base_pct
        allocated.append(trade)

    total_pct = sum(t.position_size_pct for t in allocated)
    cash_pct = round(100.0 - total_pct, 1)
    avg_prob = sum(t.probability_of_success for t in allocated) / len(allocated) if allocated else 0
    avg_conf = sum(t.confidence_score for t in allocated) / len(allocated) if allocated else 0
    high_risk = sum(1 for t in allocated if t.risk_rating == "High")
    port_risk = "High" if high_risk > len(allocated) / 2 else "Medium" if high_risk else "Low"

    max_sector = max(sector_used.values()) if sector_used else 0.0
    max_strat = max(strategy_used.values()) if strategy_used else 0.0
    # Portfolio drawdown approx: sum of trade drawdowns weighted, capped
    est_dd = sum(
        (t.estimated_drawdown_pct or 0) * (t.position_size_pct / 100)
        for t in allocated
    )
    # Also consider sum of max risks as % of portfolio
    risk_sum_pct = sum(t.maximum_risk for t in allocated) / config.portfolio_value * 100 if config.portfolio_value else 0
    est_dd = round(max(est_dd, risk_sum_pct * 0.5), 2)

    avg_eff = (
        sum(t.capital_efficiency for t in allocated) / len(allocated) if allocated else 0.0
    )

    if context.market_environment_score < 50:
        cash_pct = max(cash_pct, 60.0)
        total_pct = round(100.0 - cash_pct, 1)

    overall = port_risk
    if est_dd > config.max_portfolio_drawdown_pct * 0.5:
        overall = "High"
    elif est_dd > config.max_portfolio_drawdown_pct * 0.25:
        overall = "Medium" if overall == "Low" else overall
    if cash_pct >= 70:
        overall = f"{overall} (cash-heavy)"

    top_corr = max(corr_used.items(), key=lambda x: x[1]) if corr_used else ("n/a", 0.0)
    corr_note = f"Largest correlation cluster: {top_corr[0]} ({top_corr[1]:.1f}% capital)"

    # Re-number conviction ranks after allocation filter
    allocated_sorted = sorted(allocated, key=lambda t: t.conviction_score, reverse=True)
    for i, t in enumerate(allocated_sorted, 1):
        t.conviction_rank = i

    pure_approved = sum(1 for t in allocated if t.decision == "Approve")
    mod_count = sum(1 for t in allocated if t.decision != "Approve")

    return allocated_sorted, PortfolioSummary(
        overall_market_bias=context.overall_market_bias,
        market_environment_score=context.market_environment_score,
        total_capital_recommended_pct=round(total_pct, 1),
        cash_allocation_pct=cash_pct,
        approved_count=pure_approved,
        rejected_count=rejected_count,
        modified_count=mod_count or modified_count,
        sector_allocation={k: round(v, 1) for k, v in sector_used.items()},
        strategy_allocation={k: round(v, 1) for k, v in strategy_used.items()},
        average_probability=round(avg_prob, 2),
        average_confidence=round(avg_conf, 1),
        portfolio_risk_rating=port_risk,
        max_sector_concentration_pct=round(max_sector, 1),
        max_strategy_concentration_pct=round(max_strat, 1),
        estimated_portfolio_drawdown_pct=est_dd,
        capital_efficiency_score=round(avg_eff, 1),
        overall_portfolio_risk=overall,
        correlation_note=corr_note,
    )
