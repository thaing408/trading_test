"""Unit tests for performance pipeline and reporter."""

from trading_agent.performance.config import PerformanceConfig
from trading_agent.performance.pipeline import run_performance_pipeline
from trading_agent.performance.reporter import render_performance_report

REQUIRED_SECTIONS = [
    "## Daily Performance Metrics",
    "## Recurring Patterns",
    "## Summary of All Trades",
    "## Key Lessons Learned",
    "## Mistakes to Avoid",
    "## Areas for Improvement",
    "## Successful Habits to Reinforce",
    "## Recommended Adjustments for Tomorrow",
]

REQUIRED_TRADE_FIELDS = [
    "Entry / Exit",
    "Profit/Loss",
    "Holding Time",
    "Technical Setup",
    "News Catalyst",
    "Risk-to-Reward",
    "Confidence Score",
    "Max Drawdown",
    "MFE / MAE",
]


def test_performance_report_structure():
    config = PerformanceConfig(fixture_mode=True)
    report = run_performance_pipeline(config)
    text = render_performance_report(report)

    for section in REQUIRED_SECTIONS:
        assert section in text, f"Missing {section}"

    m = report.metrics
    assert m.trade_count == 4
    assert m.total_profit_loss != 0
    assert 0 <= m.win_rate <= 1

    for field in REQUIRED_TRADE_FIELDS:
        assert field in text, f"Missing trade field {field}"

    assert report.patterns.best_strategies or report.patterns.weakest_strategies
    assert report.lessons_learned
    assert report.tomorrow_adjustments


def test_metrics_include_strategy_sector_regime():
    config = PerformanceConfig(fixture_mode=True)
    report = run_performance_pipeline(config)
    text = render_performance_report(report)
    assert "### Strategy Performance" in text
    assert "### Sector Performance" in text
    assert "### Market Regime Performance" in text


def test_confidence_refinement_in_report():
    config = PerformanceConfig(fixture_mode=True)
    report = run_performance_pipeline(config)
    text = render_performance_report(report)
    assert "## Confidence Refinement" in text
    assert report.refinement.notes


def test_live_mode_without_trades_file_is_empty_not_fixture():
    """Live Performance must not silently load tests/fixtures/completed_trades.json."""
    from trading_agent.session.play_formatter import format_performance_plays

    config = PerformanceConfig(fixture_mode=False, trades_file=None, history_file=None)
    report = run_performance_pipeline(config)
    assert report.metrics.trade_count == 0
    assert report.metrics.total_profit_loss == 0.0
    assert report.metadata.get("trades_source") == "none"
    assert report.metadata.get("trades_is_fixture") is False
    text = format_performance_plays(report)
    assert "demo fixture" not in text
    assert "NVDA" not in text  # fixture sample trade must not appear
    assert "Data source:" in text


def test_fixture_mode_still_loads_demo_trades():
    config = PerformanceConfig(fixture_mode=True)
    report = run_performance_pipeline(config)
    assert report.metrics.trade_count == 4
    assert report.metadata.get("trades_source") == "fixture/completed_trades.json"
    assert report.metadata.get("trades_is_fixture") is True