"""Risk management standards enforcement (institutional Trading Research floors)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from trading_agent.config import RiskConfig
from trading_agent.models import OptionsMetrics, RejectedSetup, ScreenerCandidate, TechnicalAnalysis


@dataclass
class RiskEvaluation:
    passed: bool
    reasons: List[str]


def passes_risk_checks(
    candidate: ScreenerCandidate,
    technical: TechnicalAnalysis,
    options: OptionsMetrics,
    config: RiskConfig,
) -> RiskEvaluation:
    reasons: List[str] = []

    if candidate.price < config.min_price:
        reasons.append(f"Price ${candidate.price:.2f} below minimum ${config.min_price:.2f}")
    adv = candidate.avg_daily_volume or candidate.volume
    if candidate.volume < config.min_volume and adv < config.min_avg_daily_volume:
        reasons.append(
            f"Volume {candidate.volume} / ADV {adv} below minimum "
            f"{config.min_volume}/{config.min_avg_daily_volume}"
        )
    elif adv and adv < config.min_avg_daily_volume:
        reasons.append(
            f"Average daily volume {adv} below minimum {config.min_avg_daily_volume}"
        )
    elif candidate.volume < config.min_volume and not candidate.avg_daily_volume:
        reasons.append(f"Volume {candidate.volume} below minimum {config.min_volume}")
    if candidate.relative_volume < config.min_relative_volume:
        reasons.append(
            f"Relative volume {candidate.relative_volume} below minimum {config.min_relative_volume}"
        )
    if candidate.open_interest < config.min_open_interest:
        reasons.append(
            f"Open interest {candidate.open_interest} below minimum {config.min_open_interest}"
        )
    if candidate.bid_ask_spread_pct > config.max_bid_ask_spread_pct:
        reasons.append(
            f"Bid-ask spread {candidate.bid_ask_spread_pct}% exceeds max {config.max_bid_ask_spread_pct}%"
        )
    # Market cap: fail when known and below floor; unknown (0) fails live-quality bar
    if candidate.market_cap > 0 and candidate.market_cap < config.min_market_cap:
        reasons.append(
            f"Market cap ${candidate.market_cap:,.0f} below minimum ${config.min_market_cap:,.0f}"
        )
    elif candidate.market_cap <= 0:
        reasons.append("Market cap unavailable — cannot verify $2B institutional floor")
    if candidate.institutional_score and candidate.institutional_score < config.min_institutional_score:
        reasons.append(
            f"Institutional participation score {candidate.institutional_score} "
            f"below minimum {config.min_institutional_score}"
        )
    if options.liquidity_score < config.min_options_liquidity_score:
        reasons.append(
            f"Options liquidity {options.liquidity_score} below minimum {config.min_options_liquidity_score}"
        )
    if options.probability_of_profit < config.min_probability_of_success:
        reasons.append(
            f"Probability of profit {options.probability_of_profit} below minimum {config.min_probability_of_success}"
        )
    min_tech = getattr(config, "min_technical_score", 40.0)
    if technical.score < min_tech:
        reasons.append(f"Technical score {technical.score} too weak for entry")

    return RiskEvaluation(passed=len(reasons) == 0, reasons=reasons)


def evaluate_risk(
    candidates: List[Tuple[ScreenerCandidate, TechnicalAnalysis, OptionsMetrics]],
    config: RiskConfig,
) -> Tuple[List[Tuple[ScreenerCandidate, TechnicalAnalysis, OptionsMetrics]], List[RejectedSetup]]:
    qualified: List[Tuple[ScreenerCandidate, TechnicalAnalysis, OptionsMetrics]] = []
    rejected: List[RejectedSetup] = []

    for candidate, technical, options in candidates:
        result = passes_risk_checks(candidate, technical, options, config)
        if result.passed:
            qualified.append((candidate, technical, options))
        else:
            rejected.append(
                RejectedSetup(symbol=candidate.symbol, reason="; ".join(result.reasons))
            )

    return qualified, rejected
