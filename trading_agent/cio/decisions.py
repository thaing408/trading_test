"""Final CIO decision engine."""

from __future__ import annotations

from typing import List, Tuple

from trading_agent.cio.config import CIOConfig
from trading_agent.cio.evaluation import build_scorecard
from trading_agent.cio.models import (
    ApprovedTrade,
    EvaluationScorecard,
    PhaseContext,
    RejectedDecision,
    TradeCandidate,
)
from trading_agent.cio.portfolio import apply_risk_rating


def _adjusted_confidence(candidate: TradeCandidate, context: PhaseContext) -> float:
    conf = candidate.confidence_score
    conf += context.strategy_refinement.get(candidate.strategy, 0)
    conf += context.sector_refinement.get(candidate.sector, 0)
    if candidate.strategy in context.weakest_strategies:
        conf -= 10
    return max(0.0, min(100.0, conf))


def _intraday_veto(symbol: str, context: PhaseContext) -> str | None:
    action = context.intraday_flags.get(symbol, "")
    if action in ("Exit", "Hedge"):
        return f"Phase 2 recommends {action} — CIO cannot approve new/additional exposure"
    if action == "Scale Out":
        return "Phase 2 signals Scale Out — delay new allocation"
    return None


def decide_candidate(
    candidate: TradeCandidate,
    context: PhaseContext,
    config: CIOConfig,
) -> Tuple[str, str, EvaluationScorecard, List[str], ApprovedTrade | None]:
    modifications: list[str] = []
    adj_conf = _adjusted_confidence(candidate, context)
    scorecard = build_scorecard(candidate, context, config, adj_conf)

    veto = _intraday_veto(candidate.symbol, context)
    if veto:
        return "Reject", veto, scorecard, scorecard.challenges + [veto], None

    if not scorecard.catalyst_valid:
        return (
            "Reject",
            scorecard.catalyst_notes,
            scorecard,
            scorecard.challenges,
            None,
        )

    if candidate.primary_catalyst and any(
        s in candidate.primary_catalyst.lower() for s in ("reddit", "twitter", "hype")
    ):
        return (
            "Reject",
            "Rejected: speculation/social media catalyst",
            scorecard,
            scorecard.challenges,
            None,
        )

    if not scorecard.technical_pass and not scorecard.options_pass:
        return (
            "Reject",
            "Failed both technical and options quality gates",
            scorecard,
            scorecard.challenges,
            None,
        )

    if not scorecard.technical_pass:
        if scorecard.options_pass and scorecard.risk_pass and adj_conf >= config.min_confidence - 5:
            modifications.append("Reduce size 25% due to incomplete technical confirmation")
            decision = "Approve with Modifications"
        else:
            return (
                "Watchlist Only",
                f"Insufficient technical confirmation ({scorecard.technical_confirmations} signals)",
                scorecard,
                scorecard.challenges,
                None,
            )
    elif not scorecard.options_pass:
        return (
            "Delay",
            f"Options liquidity inadequate — {scorecard.options_notes}",
            scorecard,
            scorecard.challenges,
            None,
        )
    elif not scorecard.risk_pass:
        if scorecard.risk_reward_ratio >= config.min_risk_reward * 0.9:
            modifications.append(f"Tighten stop to improve R:R above {config.min_risk_reward}:1")
            decision = "Approve with Modifications"
        else:
            return (
                "Reject",
                scorecard.risk_notes,
                scorecard,
                scorecard.challenges,
                None,
            )
    elif scorecard.market_fit < 50:
        return (
            "Delay",
            f"Market regime mismatch (fit score {scorecard.market_fit:.0f})",
            scorecard,
            scorecard.challenges,
            None,
        )
    elif adj_conf < config.min_confidence:
        return (
            "Watchlist Only",
            f"Confidence {adj_conf:.0f} below institutional threshold {config.min_confidence:.0f}",
            scorecard,
            scorecard.challenges,
            None,
        )
    else:
        decision = "Approve"
        if modifications:
            decision = "Approve with Modifications"

    rr = scorecard.risk_reward_ratio
    size_mult = 0.75 if modifications else 1.0
    approved = ApprovedTrade(
        ticker=candidate.symbol,
        direction=candidate.direction,
        strategy=candidate.strategy,
        entry_price=candidate.entry_price,
        strike_prices=candidate.strike_prices,
        expiration_date=candidate.expiration,
        position_size_pct=0.0,
        dollar_allocation=0.0,
        maximum_risk=round(candidate.maximum_risk * size_mult, 2),
        maximum_reward=round(candidate.maximum_reward * size_mult, 2),
        profit_targets=[candidate.profit_target],
        stop_loss=candidate.stop_loss,
        exit_criteria="Exit at profit target, stop loss, or thesis invalidation",
        estimated_holding_period="2-5 sessions",
        probability_of_success=candidate.probability_of_success,
        confidence_score=adj_conf,
        risk_rating="Medium",
        primary_catalyst=candidate.primary_catalyst,
        technical_summary=scorecard.technical_notes,
        options_summary=scorecard.options_notes,
        key_risks=scorecard.challenges[:3] or ["Standard market risk"],
        contingency_plan="Reduce position 50% if regime shifts; exit on catalyst reversal",
        decision=decision,
        decision_explanation=_build_explanation(decision, scorecard, candidate, context),
        sector=candidate.sector,
        modifications=modifications,
    )
    apply_risk_rating(approved, rr)
    return decision, approved.decision_explanation, scorecard, scorecard.challenges, approved


def _build_explanation(
    decision: str,
    scorecard: EvaluationScorecard,
    candidate: TradeCandidate,
    context: PhaseContext,
) -> str:
    parts = [
        f"{decision}: {candidate.symbol} {candidate.strategy}",
        f"Market fit {scorecard.market_fit:.0f}/100 in {context.market_regime} regime",
        scorecard.catalyst_notes,
        scorecard.technical_notes,
        scorecard.risk_notes,
    ]
    return "; ".join(parts)


def process_all_candidates(
    candidates: List[TradeCandidate],
    context: PhaseContext,
    config: CIOConfig,
) -> Tuple[List[ApprovedTrade], List[RejectedDecision]]:
    if context.stay_in_cash and not candidates:
        return [], [
            RejectedDecision(
                ticker="PORTFOLIO",
                decision="Reject",
                explanation="Phase 1 recommends stay in cash — no capital deployment",
                challenges=["Unfavorable market conditions"],
            )
        ]

    approved: list[ApprovedTrade] = []
    rejected: list[RejectedDecision] = []

    for candidate in candidates:
        decision, explanation, scorecard, challenges, trade = decide_candidate(
            candidate, context, config
        )
        if trade and decision.startswith("Approve"):
            approved.append(trade)
        else:
            rejected.append(
                RejectedDecision(
                    ticker=candidate.symbol,
                    decision=decision,
                    explanation=explanation,
                    challenges=challenges,
                )
            )

    return approved, rejected