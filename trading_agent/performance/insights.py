"""Generate lessons, improvements, and tomorrow adjustments from analysis."""

from __future__ import annotations

from typing import List, Tuple

from trading_agent.performance.models import (
    CompletedTrade,
    ConfidenceRefinement,
    DailyMetrics,
    PatternInsights,
)


def generate_insights(
    trades: List[CompletedTrade],
    metrics: DailyMetrics,
    patterns: PatternInsights,
    refinement: ConfidenceRefinement,
) -> Tuple[List[str], List[str], List[str], List[str], List[str]]:
    lessons: list[str] = []
    mistakes: list[str] = []
    improvements: list[str] = []
    habits: list[str] = []
    tomorrow: list[str] = []

    if metrics.trade_count == 0:
        lessons.append("No completed trades today — review pre-market plan selectivity")
        tomorrow.append("Maintain capital preservation standards; only take A-grade setups")
        return lessons, mistakes, improvements, habits, tomorrow

    lessons.append(
        f"Session P/L ${metrics.total_profit_loss:+.2f} with {metrics.win_rate:.0%} win rate "
        f"and profit factor {metrics.profit_factor:.2f}"
    )

    if patterns.best_strategies:
        lessons.append(f"Best strategy today: {patterns.best_strategies[0]}")
        habits.append(f"Continue executing {patterns.best_strategies[0]} in favorable conditions")
    if patterns.weakest_strategies:
        mistakes.append(f"Avoid or tighten filters on {patterns.weakest_strategies[0]} until edge improves")
    if patterns.losing_trade_causes:
        mistakes.extend([f"Watch for: {c}" for c in patterns.losing_trade_causes[:3]])
    if patterns.profitable_conditions:
        lessons.append(f"Most profitable conditions: {', '.join(patterns.profitable_conditions[:2])}")
        tomorrow.append(f"Prioritize setups when market is {patterns.profitable_conditions[0]}")
    if patterns.top_indicator_combos:
        habits.append(f"Favor indicator combos: {patterns.top_indicator_combos[0]}")
    if patterns.top_news_catalysts:
        habits.append(f"News catalysts with edge: {patterns.top_news_catalysts[0]}")

    if metrics.average_loser > metrics.average_winner and metrics.loser_count > 0:
        improvements.append("Cut losers faster — average loser exceeds average winner")
        tomorrow.append("Tighten stop-loss discipline; exit when thesis breaks")

    if metrics.profit_factor < 1.0:
        improvements.append("Profit factor below 1.0 — review trade selection quality")
        tomorrow.append("Raise minimum confidence threshold by 5 points for tomorrow")

    for note in refinement.notes:
        if "Boost" in note or "Reduce" in note:
            tomorrow.append(note)

    winners = [t for t in trades if t.profit_loss > 0]
    if winners:
        best = max(winners, key=lambda t: t.profit_loss)
        habits.append(
            f"Replicate {best.symbol} process: {best.technical_setup} in {best.market_conditions}"
        )

    losers = [t for t in trades if t.profit_loss < 0]
    if losers:
        worst = min(losers, key=lambda t: t.profit_loss)
        mistakes.append(
            f"Review {worst.symbol} loss: {worst.strategy} with confidence {worst.confidence_score:.0f}"
        )

    # Steenbarger / Bellafiore: process metrics by setup — not P/L alone
    try:
        from trading_agent.discipline.process import process_insights_from_trades

        process_lines = process_insights_from_trades(trades)
        for line in process_lines:
            low = line.lower()
            if "habit" in low or "replicate" in low:
                habits.append(line)
            elif "improvement" in low or "review failed" in low or "missing" in low:
                improvements.append(line)
            elif "revenge" in low or "discipline" in low:
                mistakes.append(line)
            else:
                lessons.append(line)
    except Exception:
        pass

    if not improvements:
        improvements.append("Maintain current risk/reward filters and position sizing")

    return lessons, mistakes, improvements, habits, tomorrow