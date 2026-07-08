"""Calculate daily performance metrics (pure functions)."""

from __future__ import annotations

from collections import defaultdict
from typing import List

from trading_agent.performance.models import CompletedTrade, DailyMetrics


def calculate_daily_metrics(trades: List[CompletedTrade]) -> DailyMetrics:
    if not trades:
        return DailyMetrics(
            total_profit_loss=0.0,
            win_rate=0.0,
            average_winner=0.0,
            average_loser=0.0,
            profit_factor=0.0,
            expectancy=0.0,
            largest_winner=0.0,
            largest_loser=0.0,
            trade_count=0,
            winner_count=0,
            loser_count=0,
        )

    winners = [t for t in trades if t.profit_loss > 0]
    losers = [t for t in trades if t.profit_loss < 0]
    total_pl = sum(t.profit_loss for t in trades)
    gross_profit = sum(t.profit_loss for t in winners)
    gross_loss = abs(sum(t.profit_loss for t in losers))

    win_rate = len(winners) / len(trades) if trades else 0.0
    avg_winner = gross_profit / len(winners) if winners else 0.0
    avg_loser = gross_loss / len(losers) if losers else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss else float(gross_profit > 0)
    expectancy = total_pl / len(trades)

    strategy_perf: dict[str, float] = defaultdict(float)
    sector_perf: dict[str, float] = defaultdict(float)
    regime_perf: dict[str, float] = defaultdict(float)
    for t in trades:
        strategy_perf[t.strategy] += t.profit_loss
        if t.sector:
            sector_perf[t.sector] += t.profit_loss
        if t.market_regime:
            regime_perf[t.market_regime] += t.profit_loss

    return DailyMetrics(
        total_profit_loss=round(total_pl, 2),
        win_rate=round(win_rate, 4),
        average_winner=round(avg_winner, 2),
        average_loser=round(avg_loser, 2),
        profit_factor=round(profit_factor, 2),
        expectancy=round(expectancy, 2),
        largest_winner=round(max((t.profit_loss for t in winners), default=0.0), 2),
        largest_loser=round(min((t.profit_loss for t in losers), default=0.0), 2),
        trade_count=len(trades),
        winner_count=len(winners),
        loser_count=len(losers),
        strategy_performance=dict(strategy_perf),
        sector_performance=dict(sector_perf),
        regime_performance=dict(regime_perf),
    )