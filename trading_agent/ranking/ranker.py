"""Rank qualified setups by confidence score."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Tuple

from trading_agent.config import RiskConfig
from trading_agent.models import (
    OptionsMetrics,
    ScreenerCandidate,
    TechnicalAnalysis,
    TradeOpportunity,
)
from trading_agent.strategy.selector import StrategySelection, select_strategy


def compute_confidence_score(
    technical: TechnicalAnalysis,
    options: OptionsMetrics,
    candidate: ScreenerCandidate,
) -> float:
    iv_component = (
        (100 - min(options.iv_rank, 100)) * 0.05
        if options.iv_rank > 50
        else options.iv_rank * 0.05 + 2.5
    )
    score = (
        technical.score * 0.35
        + options.liquidity_score * 0.20
        + options.probability_of_profit * 100 * 0.25
        + min(candidate.relative_volume, 3.0) / 3.0 * 100 * 0.10
        + iv_component
    )
    if options.unusual_activity:
        score += 5
    return round(min(100.0, max(0.0, score)), 1)


def _trade_params(
    price: float,
    strategy: StrategySelection,
    options: OptionsMetrics,
) -> dict:
    risk_unit = price * 0.02
    if "Spread" in strategy.name or strategy.name == "Iron Condor":
        max_risk = round(risk_unit * 1.5, 2)
        max_reward = round(risk_unit * 2.0, 2)
    elif strategy.name in ("Long Call", "Long Put"):
        max_risk = round(risk_unit * 2.5, 2)
        max_reward = round(risk_unit * 5.0, 2)
    else:
        max_risk = round(risk_unit, 2)
        max_reward = round(risk_unit * 1.5, 2)

    return {
        "entry_price": round(price, 2),
        "profit_target": round(price + max_reward * 0.01, 2),
        "stop_loss": round(price - max_risk * 0.01, 2),
        "maximum_risk": max_risk,
        "maximum_reward": max_reward,
        "probability_of_success": options.probability_of_profit,
    }


def build_opportunities(
    qualified: List[Tuple[ScreenerCandidate, TechnicalAnalysis, OptionsMetrics]],
    risk_config: RiskConfig,
    max_count: int = 5,
) -> List[TradeOpportunity]:
    scored: List[Tuple[float, ScreenerCandidate, TechnicalAnalysis, OptionsMetrics, StrategySelection]] = []

    for candidate, technical, options in qualified:
        confidence = compute_confidence_score(technical, options, candidate)
        if confidence < risk_config.min_confidence_score:
            continue
        strategy = select_strategy(technical, options, candidate.price)
        scored.append((confidence, candidate, technical, options, strategy))

    scored.sort(key=lambda x: x[0], reverse=True)
    opportunities: List[TradeOpportunity] = []

    for rank, (confidence, candidate, technical, options, strategy) in enumerate(scored[:max_count], 1):
        params = _trade_params(candidate.price, strategy, options)
        expiry = (datetime.now() + timedelta(days=strategy.expiration_days)).strftime("%Y-%m-%d")
        reasons = [
            f"Technical trend: {technical.trend} with RSI {technical.rsi}",
            f"Options IV Rank {options.iv_rank}, liquidity {options.liquidity_score}",
            f"Strategy {strategy.name} matched to {strategy.bias} bias",
            f"Relative volume {candidate.relative_volume}x average",
        ]
        opportunities.append(
            TradeOpportunity(
                rank=rank,
                symbol=candidate.symbol,
                strategy=strategy.name,
                entry_price=params["entry_price"],
                strike_prices=strategy.strike_prices,
                expiration=expiry,
                profit_target=params["profit_target"],
                stop_loss=params["stop_loss"],
                maximum_risk=params["maximum_risk"],
                maximum_reward=params["maximum_reward"],
                probability_of_success=params["probability_of_success"],
                confidence_score=confidence,
                supporting_reasons=reasons,
                technical=technical,
                options=options,
            )
        )

    return opportunities