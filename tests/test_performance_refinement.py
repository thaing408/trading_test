"""Unit tests for confidence refinement."""

from trading_agent.performance.config import PerformanceConfig
from trading_agent.performance.models import CompletedTrade
from trading_agent.performance.refinement import refine_confidence


def _hist_trade(strategy: str, pl: float, regime: str = "bullish"):
    return CompletedTrade(
        symbol="X",
        entry=100.0,
        exit=100.0 + pl,
        profit_loss=pl,
        holding_time_minutes=60,
        strategy=strategy,
        technical_setup="t",
        news_catalyst="n",
        market_conditions="c",
        volatility_environment="v",
        risk_reward_ratio=2.0,
        probability_of_success=0.5,
        confidence_score=60.0,
        position_size=1,
        max_drawdown=10.0,
        max_favorable_excursion=20.0,
        max_adverse_excursion=10.0,
        sector="Tech",
        market_regime=regime,
    )


def test_refinement_bounded_and_respects_min_trades():
    config = PerformanceConfig(min_trades_for_refinement=5, max_confidence_adjustment=10.0)
    r = refine_confidence([_hist_trade("Spread", 100)], config)
    assert not r.strategy_adjustments
    assert any("Insufficient" in n for n in r.notes)


def test_refinement_produces_strategy_adjustments():
    history = [
        _hist_trade("Spread", 200),
        _hist_trade("Spread", 150),
        _hist_trade("Long Call", -100),
        _hist_trade("Long Call", -80),
        _hist_trade("Spread", 100, "bullish"),
    ]
    config = PerformanceConfig(min_trades_for_refinement=3, max_confidence_adjustment=10.0)
    r = refine_confidence(history, config)
    assert r.strategy_adjustments
    assert all(abs(v) <= 10.0 for v in r.strategy_adjustments.values())