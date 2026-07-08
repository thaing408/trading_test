"""Identify recurring performance patterns (pure functions)."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import List

from trading_agent.performance.models import CompletedTrade, PatternInsights


def _hour_bucket(entry_time: str) -> str:
    if not entry_time or ":" not in entry_time:
        return "unknown"
    hour = int(entry_time.split(":")[0])
    if hour < 10:
        return "open (09:30-10:00)"
    if hour < 12:
        return "morning (10:00-12:00)"
    if hour < 14:
        return "midday (12:00-14:00)"
    return "afternoon (14:00-16:00)"


def identify_patterns(trades: List[CompletedTrade]) -> PatternInsights:
    if not trades:
        return PatternInsights(
            best_strategies=[],
            weakest_strategies=[],
            losing_trade_causes=[],
            profitable_conditions=[],
            time_of_day_performance={},
            top_indicator_combos=[],
            top_news_catalysts=[],
        )

    strategy_pl: dict[str, float] = defaultdict(float)
    condition_pl: dict[str, float] = defaultdict(float)
    time_pl: dict[str, float] = defaultdict(float)
    indicator_pl: dict[str, float] = defaultdict(float)
    catalyst_pl: dict[str, float] = defaultdict(float)
    loss_causes: Counter[str] = Counter()

    for t in trades:
        strategy_pl[t.strategy] += t.profit_loss
        condition_pl[t.market_conditions] += t.profit_loss
        time_pl[_hour_bucket(t.entry_time)] += t.profit_loss
        if t.indicator_combo:
            indicator_pl[t.indicator_combo] += t.profit_loss
        if t.news_catalyst:
            catalyst_pl[t.news_catalyst] += t.profit_loss
        if t.profit_loss < 0:
            if t.max_adverse_excursion > abs(t.profit_loss) * 1.5:
                loss_causes["excessive adverse excursion before exit"] += 1
            if t.volatility_environment.lower().find("high") >= 0:
                loss_causes["high volatility environment"] += 1
            if t.confidence_score < 55:
                loss_causes["low pre-trade confidence (<55)"] += 1
            if t.risk_reward_ratio < 1.5:
                loss_causes["poor risk-to-reward setup (<1.5)"] += 1
            if not t.news_catalyst or t.news_catalyst.lower() == "none":
                loss_causes["no supporting news catalyst"] += 1

    ranked_strategies = sorted(strategy_pl.items(), key=lambda x: x[1], reverse=True)
    ranked_conditions = sorted(condition_pl.items(), key=lambda x: x[1], reverse=True)
    ranked_indicators = sorted(indicator_pl.items(), key=lambda x: x[1], reverse=True)
    ranked_catalysts = sorted(catalyst_pl.items(), key=lambda x: x[1], reverse=True)

    return PatternInsights(
        best_strategies=[s for s, _ in ranked_strategies[:3] if strategy_pl[s] > 0],
        weakest_strategies=[s for s, p in ranked_strategies if p < 0][-3:][::-1]
        or [s for s, _ in ranked_strategies[-3:]],
        losing_trade_causes=[f"{cause} ({count}x)" for cause, count in loss_causes.most_common(5)],
        profitable_conditions=[c for c, p in ranked_conditions[:3] if p > 0],
        time_of_day_performance={k: round(v, 2) for k, v in sorted(time_pl.items())},
        top_indicator_combos=[f"{c} (${p:+.0f})" for c, p in ranked_indicators[:3]],
        top_news_catalysts=[f"{c} (${p:+.0f})" for c, p in ranked_catalysts[:3]],
    )