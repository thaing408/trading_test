"""Unit tests for performance metrics calculation."""

from trading_agent.performance.metrics import calculate_daily_metrics
from trading_agent.performance.models import CompletedTrade


def _trade(pl: float, strategy: str = "Long Call", sector: str = "Tech", regime: str = "bullish"):
    return CompletedTrade(
        symbol="TEST",
        entry=100.0,
        exit=100.0 + pl,
        profit_loss=pl,
        holding_time_minutes=60,
        strategy=strategy,
        technical_setup="test",
        news_catalyst="none",
        market_conditions="bullish",
        volatility_environment="moderate",
        risk_reward_ratio=2.0,
        probability_of_success=0.5,
        confidence_score=60.0,
        position_size=1,
        max_drawdown=10.0,
        max_favorable_excursion=20.0,
        max_adverse_excursion=10.0,
        sector=sector,
        market_regime=regime,
    )


def test_daily_metrics_win_rate_and_profit_factor():
    trades = [_trade(100), _trade(50), _trade(-30)]
    m = calculate_daily_metrics(trades)
    assert m.trade_count == 3
    assert m.winner_count == 2
    assert m.loser_count == 1
    assert m.total_profit_loss == 120.0
    assert m.win_rate == round(2 / 3, 4)
    assert m.profit_factor == round(150 / 30, 2)
    assert m.expectancy == 40.0


def test_strategy_sector_regime_breakdown():
    trades = [
        _trade(100, strategy="Spread", sector="Tech", regime="bullish"),
        _trade(-50, strategy="Long Call", sector="Energy", regime="bearish"),
    ]
    m = calculate_daily_metrics(trades)
    assert m.strategy_performance["Spread"] == 100
    assert m.sector_performance["Energy"] == -50
    assert m.regime_performance["bearish"] == -50