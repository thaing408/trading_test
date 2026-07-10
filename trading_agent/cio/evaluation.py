"""CIO decision framework evaluators (pure functions)."""

from __future__ import annotations

from collections import Counter

from trading_agent.cio.config import CIOConfig
from trading_agent.cio.models import EvaluationScorecard, PhaseContext, TradeCandidate

SPECULATIVE_CATALYSTS = {"social media", "reddit", "twitter", "hype", "rumor", "speculation"}
VALID_CATALYSTS = {
    "earnings", "analyst", "contract", "sec_filing", "institutional",
    "sector_momentum", "technical_breakout", "macro", "industry_news", "insider",
}

# Map candidate sector names to strength proxies when MI sector_strength missing
SECTOR_ALIASES = {
    "technology": "XLK",
    "financials": "XLF",
    "energy": "XLE",
    "healthcare": "XLV",
    "consumer": "XLY",
    "semiconductors": "SMH",
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
    elif context.market_environment_score < 55:
        score -= 5
        challenges.append(f"Suboptimal environment score ({context.market_environment_score})")

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


def evaluate_sector_strength(
    candidate: TradeCandidate,
    context: PhaseContext,
) -> tuple[bool, str, list[str]]:
    challenges: list[str] = []
    sector = (candidate.sector or "").strip()
    strength_map = context.sector_strength or {}
    refinement = context.sector_refinement or {}

    # Prefer explicit MI strength; else use refinement; else pass with neutral note
    key = sector
    alias = SECTOR_ALIASES.get(sector.lower(), "")
    strength = None
    if key in strength_map:
        strength = strength_map[key]
    elif alias and alias in strength_map:
        strength = strength_map[alias]
    elif sector in refinement:
        strength = refinement[sector]

    if strength is None:
        return True, f"Sector {sector or 'n/a'}: strength data unavailable — neutral", challenges

    if strength < -0.5 and candidate.direction.lower() == "bullish":
        challenges.append(f"Bullish trade in weak sector {sector} ({strength:+.2f})")
        return False, f"Sector {sector} lagging ({strength:+.2f})", challenges
    if strength > 0.5 and candidate.direction.lower() == "bearish":
        challenges.append(f"Bearish trade against strong sector {sector} ({strength:+.2f})")
        return False, f"Sector {sector} leading ({strength:+.2f})", challenges

    tone = "strong" if strength > 0.2 else "weak" if strength < -0.2 else "neutral"
    return True, f"Sector {sector} {tone} ({strength:+.2f})", challenges


def evaluate_capital_efficiency(candidate: TradeCandidate, rr: float) -> tuple[float, str]:
    """Score capital efficiency 0-100 from R:R, POP, liquidity, risk dollars."""
    pop = candidate.probability_of_success or candidate.probability_of_profit
    liq = candidate.liquidity_score
    score = (
        min(40.0, rr * 12.0)
        + min(30.0, pop * 50.0)
        + min(20.0, liq * 0.2)
        + (10.0 if candidate.maximum_risk > 0 and candidate.maximum_reward >= candidate.maximum_risk * 2 else 0.0)
    )
    score = max(0.0, min(100.0, score))
    notes = f"Capital efficiency {score:.0f}/100 (R:R {rr:.1f}, POP {pop:.0%}, liq {liq:.0f})"
    return round(score, 1), notes


def estimate_trade_drawdown_pct(candidate: TradeCandidate, portfolio_value: float) -> float:
    """Worst-case loss as % of portfolio if full max risk is realized on a unit notionals proxy."""
    if portfolio_value <= 0:
        return 0.0
    # Use maximum_risk as dollar risk estimate when already in dollars
    risk = candidate.maximum_risk
    return round(min(100.0, risk / portfolio_value * 100), 2)


def evaluate_hedge_fund_standard(
    scorecard_partial: dict,
    adj_conf: float,
    config: CIOConfig,
) -> tuple[bool, str]:
    """Would a professional desk approve? Requires all hard gates + confidence."""
    required = [
        scorecard_partial.get("catalyst_valid"),
        scorecard_partial.get("technical_pass"),
        scorecard_partial.get("options_pass"),
        scorecard_partial.get("risk_pass"),
        scorecard_partial.get("sector_strength_pass"),
        scorecard_partial.get("market_fit", 0) >= 50,
        adj_conf >= config.min_confidence,
        scorecard_partial.get("capital_efficiency", 0) >= 45,
    ]
    if all(required):
        return True, "Yes — meets institutional gate stack (regime, catalyst, tech, liquidity, R:R, sector)"
    missing = []
    if not scorecard_partial.get("catalyst_valid"):
        missing.append("catalyst")
    if not scorecard_partial.get("technical_pass"):
        missing.append("technicals")
    if not scorecard_partial.get("options_pass"):
        missing.append("options liquidity")
    if not scorecard_partial.get("risk_pass"):
        missing.append("risk/R:R/prob")
    if not scorecard_partial.get("sector_strength_pass"):
        missing.append("sector")
    if scorecard_partial.get("market_fit", 0) < 50:
        missing.append("regime fit")
    if adj_conf < config.min_confidence:
        missing.append("conviction")
    if scorecard_partial.get("capital_efficiency", 0) < 45:
        missing.append("capital efficiency")
    return False, "No — fails: " + (", ".join(missing) if missing else "standards")


def compute_conviction(
    market_fit: float,
    adj_conf: float,
    rr: float,
    pop: float,
    capital_efficiency: float,
    tech_pass: bool,
    opt_pass: bool,
    cat_valid: bool,
) -> float:
    score = (
        market_fit * 0.20
        + adj_conf * 0.30
        + min(100.0, rr * 25.0) * 0.15
        + pop * 100 * 0.15
        + capital_efficiency * 0.20
    )
    if not tech_pass:
        score *= 0.85
    if not opt_pass:
        score *= 0.80
    if not cat_valid:
        score *= 0.50
    return round(max(0.0, min(100.0, score)), 1)


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
    sector_pass, sector_notes, s_challenges = evaluate_sector_strength(candidate, context)
    efficiency, eff_notes = evaluate_capital_efficiency(candidate, rr)
    dd_pct = estimate_trade_drawdown_pct(candidate, config.portfolio_value)

    corr_group = candidate.correlation_group or candidate.sector or "unspecified"
    corr_notes = f"Correlation group: {corr_group}"

    partial = {
        "catalyst_valid": cat_valid,
        "technical_pass": tech_pass,
        "options_pass": opt_pass,
        "risk_pass": risk_pass,
        "sector_strength_pass": sector_pass,
        "market_fit": market_fit,
        "capital_efficiency": efficiency,
    }
    hf_ok, hf_notes = evaluate_hedge_fund_standard(partial, adjusted_confidence, config)

    conviction = compute_conviction(
        market_fit,
        adjusted_confidence,
        rr,
        candidate.probability_of_success,
        efficiency,
        tech_pass,
        opt_pass,
        cat_valid,
    )

    all_challenges = m_challenges + c_challenges + t_challenges + o_challenges + r_challenges + s_challenges
    if dd_pct > config.max_daily_loss_pct * 2:
        all_challenges.append(
            f"Trade max loss ~{dd_pct:.1f}% of portfolio exceeds comfort vs daily loss policy"
        )

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
        sector_strength_pass=sector_pass,
        sector_notes=sector_notes,
        correlation_notes=corr_notes,
        capital_efficiency=efficiency,
        capital_efficiency_notes=eff_notes,
        estimated_trade_drawdown_pct=dd_pct,
        hedge_fund_standard=hf_ok,
        hedge_fund_notes=hf_notes,
        conviction_score=conviction,
    )


def correlation_concentration_note(candidates: list[TradeCandidate]) -> str:
    groups = Counter((c.correlation_group or c.sector or "Other") for c in candidates)
    if not groups:
        return "No approved book — correlation N/A"
    top, n = groups.most_common(1)[0]
    return f"Highest correlation cluster: {top} ({n} names)"
