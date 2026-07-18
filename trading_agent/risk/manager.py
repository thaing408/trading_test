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


def liquid_mid_price_eligible(candidate: ScreenerCandidate, config: RiskConfig) -> bool:
    """True when sub-min_price name qualifies via high ADV / $ volume exception.

    Used for liquid mid-price names (e.g. LCID) without lowering the $20 floor
    for the entire universe.
    """
    if not getattr(config, "allow_liquid_mid_price", False):
        return False
    floor = float(getattr(config, "liquid_mid_min_price", 5.0) or 5.0)
    if candidate.price < floor:
        return False
    if candidate.price >= float(config.min_price):
        return True  # already institutional price band
    adv = float(candidate.avg_daily_volume or candidate.volume or 0)
    min_adv = float(getattr(config, "liquid_mid_min_avg_daily_volume", 5_000_000) or 0)
    if adv < min_adv:
        return False
    dollar_vol = float(candidate.price) * adv
    min_dv = float(getattr(config, "liquid_mid_min_dollar_volume", 30_000_000) or 0)
    if dollar_vol < min_dv:
        return False
    min_mcap = float(getattr(config, "liquid_mid_min_market_cap", 1_000_000_000) or 0)
    if candidate.market_cap > 0 and candidate.market_cap < min_mcap:
        return False
    if candidate.market_cap <= 0:
        return False  # fail-closed on unknown mcap for exception path
    min_rvol = float(getattr(config, "liquid_mid_min_relative_volume", 1.5) or 0)
    if candidate.relative_volume < min_rvol:
        return False
    return True


def passes_risk_checks(
    candidate: ScreenerCandidate,
    technical: TechnicalAnalysis,
    options: OptionsMetrics,
    config: RiskConfig,
) -> RiskEvaluation:
    reasons: List[str] = []

    mid_ok = liquid_mid_price_eligible(candidate, config)
    if candidate.price < config.min_price and not mid_ok:
        reasons.append(
            f"Price ${candidate.price:.2f} below minimum ${config.min_price:.2f}"
            + (
                " (liquid mid-price exception off or liquidity floors not met)"
                if getattr(config, "allow_liquid_mid_price", False)
                else ""
            )
        )
    elif candidate.price < config.min_price and mid_ok:
        # Price exception granted — still enforce liquid mid ADV/$ volume (already checked)
        pass

    # Volume floors: use liquid mid ADV when exception path is active
    adv = candidate.avg_daily_volume or candidate.volume
    vol_floor = config.min_volume
    adv_floor = config.min_avg_daily_volume
    if mid_ok and candidate.price < config.min_price:
        adv_floor = max(
            adv_floor,
            int(getattr(config, "liquid_mid_min_avg_daily_volume", adv_floor) or adv_floor),
        )
        vol_floor = min(vol_floor, adv_floor)  # session vol may lag; ADV carries

    if candidate.volume < vol_floor and adv < adv_floor:
        reasons.append(
            f"Volume {candidate.volume} / ADV {adv} below minimum "
            f"{vol_floor}/{adv_floor}"
        )
    elif adv and adv < adv_floor:
        reasons.append(
            f"Average daily volume {adv} below minimum {adv_floor}"
        )
    elif candidate.volume < vol_floor and not candidate.avg_daily_volume:
        reasons.append(f"Volume {candidate.volume} below minimum {vol_floor}")

    rvol_floor = config.min_relative_volume
    if mid_ok and candidate.price < config.min_price:
        rvol_floor = min(
            rvol_floor,
            float(getattr(config, "liquid_mid_min_relative_volume", rvol_floor) or rvol_floor),
        )
    if candidate.relative_volume < rvol_floor:
        reasons.append(
            f"Relative volume {candidate.relative_volume} below minimum {rvol_floor}"
        )
    if candidate.open_interest < config.min_open_interest:
        reasons.append(
            f"Open interest {candidate.open_interest} below minimum {config.min_open_interest}"
        )
    if candidate.bid_ask_spread_pct > config.max_bid_ask_spread_pct:
        reasons.append(
            f"Bid-ask spread {candidate.bid_ask_spread_pct}% exceeds max {config.max_bid_ask_spread_pct}%"
        )
    # Market cap: liquid mid uses softer $1B floor for sub-$20 names
    mcap_floor = config.min_market_cap
    if mid_ok and candidate.price < config.min_price:
        mcap_floor = float(
            getattr(config, "liquid_mid_min_market_cap", mcap_floor) or mcap_floor
        )
    if candidate.market_cap > 0 and candidate.market_cap < mcap_floor:
        reasons.append(
            f"Market cap ${candidate.market_cap:,.0f} below minimum ${mcap_floor:,.0f}"
        )
    elif candidate.market_cap <= 0:
        reasons.append("Market cap unavailable — cannot verify institutional floor")
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
