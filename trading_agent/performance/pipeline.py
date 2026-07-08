"""Orchestrate performance review pipeline."""

from __future__ import annotations

from datetime import datetime, timezone

from trading_agent.performance.config import PerformanceConfig
from trading_agent.performance.insights import generate_insights
from trading_agent.performance.loader import load_history, load_trades
from trading_agent.performance.metrics import calculate_daily_metrics
from trading_agent.performance.models import PerformanceReport
from trading_agent.performance.patterns import identify_patterns
from trading_agent.performance.refinement import refine_confidence


def run_performance_pipeline(config: PerformanceConfig) -> PerformanceReport:
    trades = load_trades(config.trades_file, config.fixture_mode)
    history = load_history(config.history_file, config.fixture_mode)
    all_history = history + trades

    metrics = calculate_daily_metrics(trades)
    patterns = identify_patterns(all_history if all_history else trades)
    refinement = refine_confidence(all_history, config)

    lessons, mistakes, improvements, habits, tomorrow = generate_insights(
        trades, metrics, patterns, refinement
    )

    return PerformanceReport(
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        trades=trades,
        metrics=metrics,
        patterns=patterns,
        refinement=refinement,
        lessons_learned=lessons,
        mistakes_to_avoid=mistakes,
        areas_for_improvement=improvements,
        successful_habits=habits,
        tomorrow_adjustments=tomorrow,
        metadata={
            "trades_source": config.trades_file or "fixture/completed_trades.json",
            "history_count": len(history),
            "session_trade_count": len(trades),
        },
    )