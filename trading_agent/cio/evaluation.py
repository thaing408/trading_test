"""CIO decision framework evaluators (pure functions)."""

from __future__ import annotations

from trading_agent.cio.config import CIOConfig
from trading_agent.cio.models import EvaluationScorecard, PhaseContext, TradeCandidate

SPECULATIVE_CATALYSTS = {"social media", "reddit", "twitter", "hype", "rumor", "speculation"}
VALID_CATALYSTS = {
    "earnings", "analyst", "contract", "sec_filing", "institutional",
    "sector_momentum", "technical_breakout", "macro", "industry_news", "insider",
}


def evaluate_market_fit(candidate: TradeCandidate, context: PhaseContext) -> tuple[float, list[str]]:
    challenges: list[str] = []
    score = 50.0
    regime = context.market_regime.lower()
    direction = candidate.direction.lower()

    if regime == "bullish" and direction == "bullish":
        score += 20
    elif regime == "bearish" and direction == "bearish":
        score += 20
    elif regime == "neutral" and direction == "neutral":
        score += 15
    elif regime == "bullish" and direction == "bearish":
        score -= 25
        challenges.append("Strategy direction conflicts with bullish regime")
    elif regime == "bearish" and direction == "bullish":
        score -= 25
        challenges.append("Bullish trade in bearish regime")

    if "high" in candidate.options_summary.lower() or candidate.iv_rank > 60:
        if "Condor" in candidate.strategy or "Credit" in candidate.strategy:
            score += 10
        elif "Long Call" in candidate.strategy or "Debit" in candidate.strategy:
            challenges.append("Long premium in elevated IV — poor capital efficiency")

    if context.market_environment_score < 45:
        score -= 15
        challenges.append(f"Low environment score ({context.market_environment_score})")

    return max(0.0, min(100.0, score)), challenges


def validate_catalyst(candidate: TradeCandidate) -> tuple[bool, str, list[str]]:
    challenges: list[str] = []
    cat_type = candidate.catalyst_type.lower().replace(" ", "_")
    catalyst_lower = candidate.primary_catalyst.lower()

    if any(s in catalyst_lower for s in SPECULATIVE_CATALYSTS):
        return False, "Speculative/social media catalyst — rejected", ["No legitimate institutional catalyst"]

    if cat_type in VALID_CATALYSTS or any(v in catalyst_lower for v in VALID_CATALYSTS):
        return True, f"Validated catalyst: {candidate.primary_catalyst}", challenges

    if candidate.primary_catalyst and candidate.primary_catalyst.lower() not in ("none", "n/a", ""):
        return True, f"Acceptable catalyst: {candidate.primary_catalyst}", challenges

    challenges.append("No identifiable catalyst")
    return False, "Missing legitimate catalyst", challenges


def confirm_technical(candidate: TradeCandidate, config: CIOConfig) -> tuple[bool, int, str, list[str]]:
    challenges: list[str] = []
    count = len(candidate.technical_confirmations)
    notes = candidate.technical_summary
    if count < config.min_technical_confirmations:
        challenges.append(
            f"Only {count} technical confirmations; need {config.min_technical_confirmations}"
        )
        return False, count, notes, challenges
    return True, count, f"{count} independent confirmations: {', '.join(candidate.technical_confirmations[:4])}", challenges


def evaluate_options_quality(candidate: TradeCandidate, config: CIOConfig) -> tuple[bool, str, list[str]]:
    challenges: list[str] = []
    issues: list[str] = []

    if candidate.open_interest < config.min_open_interest:
        issues.append(f"OI {candidate.open_interest} < {config.min_open_interest}")
    if candidate.daily_options_volume < config.min_options_volume:
        issues.append(f"Volume {candidate.daily_options_volume} < {config.min_options_volume}")
    if candidate.bid_ask_spread_pct > config.max_bid_ask_spread_pct:
        issues.append(f"Spread {candidate.bid_ask_spread_pct}% > {config.max_bid_ask_spread_pct}%")
    if candidate.liquidity_score < config.min_liquidity_score:
        issues.append(f"Liquidity {candidate.liquidity_score} < {config.min_liquidity_score}")

    if issues:
        challenges.extend(issues)
        return False, "; ".join(issues), challenges

    summary = (
        f"OI {candidate.open_interest:,}, vol {candidate.daily_options_volume:,}, "
        f"spread {candidate.bid_ask_spread_pct:.1f}%, IV rank {candidate.iv_rank:.0f}, "
        f"POP {candidate.probability_of_profit:.0%}, liquidity {candidate.liquidity_score:.0f}"
    )
    return True, summary, challenges


def evaluate_risk(
    candidate: TradeCandidate,
    config: CIOConfig,
    adjusted_confidence: float,
) -> tuple[bool, float, str, list[str]]:
    challenges: list[str] = []
    rr = candidate.maximum_reward / candidate.maximum_risk if candidate.maximum_risk else 0

    if rr < config.min_risk_reward:
        challenges.append(f"R:R {rr:.1f}:1 below minimum {config.min_risk_reward}:1")
    if candidate.probability_of_success < config.min_probability:
        challenges.append(
            f"Probability {candidate.probability_of_success:.0%} below {config.min_probability:.0%}"
        )
    if adjusted_confidence < config.min_confidence:
        challenges.append(f"Confidence {adjusted_confidence:.0f} below {config.min_confidence:.0f}")

    passed = len(challenges) == 0
    notes = f"R:R {rr:.1f}:1, prob {candidate.probability_of_success:.0%}, conf {adjusted_confidence:.0f}"
    return passed, rr, notes, challenges


def build_scorecard(
    candidate: TradeCandidate,
    context: PhaseContext,
    config: CIOConfig,
    adjusted_confidence: float,
) -> EvaluationScorecard:
    market_fit, m_challenges = evaluate_market_fit(candidate, context)
    cat_valid, cat_notes, c_challenges = validate_catalyst(candidate)
    tech_pass, tech_count, tech_notes, t_challenges = confirm_technical(candidate, config)
    opt_pass, opt_notes, o_challenges = evaluate_options_quality(candidate, config)
    risk_pass, rr, risk_notes, r_challenges = evaluate_risk(candidate, config, adjusted_confidence)

    all_challenges = m_challenges + c_challenges + t_challenges + o_challenges + r_challenges

    return EvaluationScorecard(
        market_fit=market_fit,
        catalyst_valid=cat_valid,
        catalyst_notes=cat_notes,
        technical_confirmations=tech_count,
        technical_pass=tech_pass,
        technical_notes=tech_notes,
        options_pass=opt_pass,
        options_notes=opt_notes,
        risk_reward_ratio=rr,
        risk_pass=risk_pass,
        risk_notes=risk_notes,
        challenges=all_challenges,
    )