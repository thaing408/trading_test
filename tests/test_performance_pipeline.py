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
    assert "empty journal" in text
    assert "live journal" not in text


def test_fixture_mode_still_loads_demo_trades():
    config = PerformanceConfig(fixture_mode=True)
    report = run_performance_pipeline(config)
    assert report.metrics.trade_count == 4
    assert report.metadata.get("trades_source") == "fixture/completed_trades.json"
    assert report.metadata.get("trades_is_fixture") is True

def test_live_journal_label_when_trades_present(tmp_path):
    from trading_agent.session.play_formatter import format_performance_plays
    from trading_agent.performance.config import PerformanceConfig
    from trading_agent.performance.pipeline import run_performance_pipeline
    import json
    trades = {
        "trades": [
            {
                "symbol": "QQQ",
                "entry": 1.0,
                "exit": 1.3,
                "profit_loss": 30.0,
                "holding_time_minutes": 10,
                "strategy": "Long Call",
                "technical_setup": "breakout",
                "news_catalyst": "none",
                "market_conditions": "bullish",
                "volatility_environment": "low",
                "risk_reward_ratio": 1.5,
                "probability_of_success": 0.5,
                "confidence_score": 60.0,
                "position_size": 1,
                "max_drawdown": 5.0,
                "max_favorable_excursion": 35.0,
                "max_adverse_excursion": 5.0,
            }
        ]
    }
    path = tmp_path / "real_trades.json"
    path.write_text(json.dumps(trades), encoding="utf-8")
    report = run_performance_pipeline(
        PerformanceConfig(fixture_mode=False, trades_file=str(path), history_file=None)
    )
    text = format_performance_plays(report)
    assert report.metrics.trade_count == 1
    assert "live journal" in text
    assert "empty journal" not in text
    assert "demo fixture" not in text
