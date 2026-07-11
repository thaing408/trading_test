"""Final CIO decision engine — challenge every assumption; capital preservation first."""

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


def _why_it_works(candidate: TradeCandidate, scorecard: EvaluationScorecard, context: PhaseContext) -> str:
    return (
        f"Works if {context.market_regime} regime holds, catalyst ({candidate.primary_catalyst}) "
        f"remains valid, technicals ({scorecard.technical_notes}) persist, and "
        f"options liquidity stays adequate ({scorecard.options_notes}). "
        f"R:R {scorecard.risk_reward_ratio:.1f}:1 with POP {candidate.probability_of_success:.0%} "
        f"supports positive expectancy under sized risk."
    )


def _why_it_fails(candidate: TradeCandidate, scorecard: EvaluationScorecard) -> str:
    fails = list(scorecard.challenges[:3]) if scorecard.challenges else []
    fails.append("Adverse gap through stop / vol crush against long premium")
    fails.append("Regime flip invalidating directional bias")
    return "; ".join(fails[:4])


def _thesis_invalidation(candidate: TradeCandidate, context: PhaseContext) -> str:
    return (
        f"Invalidate if: (1) price closes beyond stop ${candidate.stop_loss:.2f}; "
        f"(2) catalyst reversed or proven false; "
        f"(3) market regime shifts away from {candidate.direction.lower()} "
        f"(env score collapse or opposite futures trend); "
        f"(4) options liquidity deteriorates beyond CIO floors."
    )


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

    # Elevated uncertainty: refuse new risk even if research proposed names
    if context.stay_in_cash:
        return (
            "Reject",
            "Capital preservation: research/phase stay-in-cash — no new deployment",
            scorecard,
            scorecard.challenges + ["Stay-in-cash mandate"],
            None,
        )
    if context.market_environment_score < 42:
        return (
            "Reject",
            f"Elevated uncertainty (environment {context.market_environment_score:.0f}) — remain in cash",
            scorecard,
            scorecard.challenges + ["Environment too weak for deployment"],
            None,
        )

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

    if not scorecard.sector_strength_pass:
        return (
            "Reject",
            scorecard.sector_notes,
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

    decision = "Approve"

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
    elif not scorecard.hedge_fund_standard:
        # Soft path: only allow as modified if close; else reject
        if scorecard.conviction_score >= config.min_confidence - 5 and scorecard.risk_pass:
            modifications.append("Size cut 30% — fails full hedge-fund standard stack")
            decision = "Approve with Modifications"
        else:
            return (
                "Reject",
                scorecard.hedge_fund_notes,
                scorecard,
                scorecard.challenges,
                None,
            )
    else:
        decision = "Approve"
        if modifications:
            decision = "Approve with Modifications"

    if scorecard.capital_efficiency < 45 and decision.startswith("Approve"):
        modifications.append("Reduce size 20% — capital efficiency below institutional bar")
        decision = "Approve with Modifications"

    rr = scorecard.risk_reward_ratio
    size_mult = 0.75 if modifications else 1.0
    why_works = _why_it_works(candidate, scorecard, context)
    why_fails = _why_it_fails(candidate, scorecard)
    invalidation = _thesis_invalidation(candidate, context)
    hf = "Yes" if scorecard.hedge_fund_standard and decision == "Approve" else scorecard.hedge_fund_notes

    grade = getattr(candidate, "setup_grade", "C") or "C"
    hold = getattr(candidate, "hold_style", "") or ""
    if grade in ("A+", "A"):
        hold_period = "3-10 sessions (A-tier runner / swing)"
        size_mult *= 1.0 if grade == "A+" else 0.95
    elif grade == "B":
        hold_period = "2-5 sessions (standard)"
        size_mult *= 0.85
    elif grade == "C":
        hold_period = "1-3 sessions (early take-profit)"
        size_mult *= 0.6
        if decision == "Approve":
            modifications.append("Grade C — reduce size and take profit early")
            decision = "Approve with Modifications"
    else:
        hold_period = "0 — grade F no deployment"
        size_mult = 0.0

    if hold:
        modifications = list(modifications)
        if hold not in modifications:
            modifications.append(f"Hold style ({grade}): {hold}")

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
        exit_criteria=invalidation,
        estimated_holding_period=hold_period,
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
        conviction_score=scorecard.conviction_score,
        why_it_works=why_works,
        why_it_fails=why_fails,
        thesis_invalidation=invalidation,
        hedge_fund_approve=hf,
        reward_to_risk=round(rr, 2),
        capital_efficiency=scorecard.capital_efficiency,
        estimated_drawdown_pct=scorecard.estimated_trade_drawdown_pct,
        correlation_group=candidate.correlation_group or candidate.sector,
        setup_grade=grade,
        grade_score=float(getattr(candidate, "grade_score", 0.0) or 0.0),
        hold_style=hold,
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
        scorecard.sector_notes,
        scorecard.risk_notes,
        scorecard.capital_efficiency_notes,
        f"Conviction {scorecard.conviction_score:.0f}",
        scorecard.hedge_fund_notes,
    ]
    return "; ".join(p for p in parts if p)


def process_all_candidates(
    candidates: List[TradeCandidate],
    context: PhaseContext,
    config: CIOConfig,
) -> Tuple[List[ApprovedTrade], List[ApprovedTrade], List[RejectedDecision]]:
    """Return (approved, modified, rejected) ranked by conviction within each bucket."""
    if context.stay_in_cash and not candidates:
        return [], [], [
            RejectedDecision(
                ticker="PORTFOLIO",
                decision="Reject",
                explanation="Phase 1 recommends stay in cash — no capital deployment",
                challenges=["Unfavorable market conditions"],
                why_it_fails="Stay-in-cash mandate from research",
                thesis_invalidation="N/A — no trade",
                hedge_fund_approve="No — capital preservation",
            )
        ]

    if context.market_environment_score < 42:
        return [], [], [
            RejectedDecision(
                ticker="PORTFOLIO",
                decision="Reject",
                explanation="Elevated uncertainty — CIO mandates cash",
                challenges=[f"Environment score {context.market_environment_score}"],
                why_it_fails="Macro/regime uncertainty too high",
                thesis_invalidation="Remain flat until environment improves",
                hedge_fund_approve="No",
            )
        ]

    approved: list[ApprovedTrade] = []
    modified: list[ApprovedTrade] = []
    rejected: list[RejectedDecision] = []

    for candidate in candidates:
        decision, explanation, scorecard, challenges, trade = decide_candidate(
            candidate, context, config
        )
        if trade and decision == "Approve":
            approved.append(trade)
        elif trade and decision == "Approve with Modifications":
            modified.append(trade)
        else:
            rejected.append(
                RejectedDecision(
                    ticker=candidate.symbol,
                    decision=decision,
                    explanation=explanation,
                    challenges=challenges,
                    why_it_fails=_why_it_fails(candidate, scorecard),
                    thesis_invalidation=_thesis_invalidation(candidate, context),
                    hedge_fund_approve="No",
                )
            )

    # A+/A first, then conviction within grade
    from trading_agent.ranking.grades import GRADE_RANK

    def _cio_sort_key(t: ApprovedTrade):
        g = getattr(t, "setup_grade", "C") or "C"
        return (GRADE_RANK.get(g, 99), -t.conviction_score, -float(getattr(t, "grade_score", 0) or 0))

    approved.sort(key=_cio_sort_key)
    modified.sort(key=_cio_sort_key)
    for i, t in enumerate(approved, 1):
        t.conviction_rank = i
    for i, t in enumerate(modified, 1):
        t.conviction_rank = i

    return approved, modified, rejected
