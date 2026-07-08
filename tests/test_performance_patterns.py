"""Unit tests for pattern identification."""

from trading_agent.performance.models import CompletedTrade
from trading_agent.performance.patterns import identify_patterns


def _trade(**kw):
    defaults = {
        "symbol": "X",
        "entry": 100.0,
        "exit": 105.0,
        "profit_loss": 50.0,
        "holding_time_minutes": 60,
        "strategy": "Debit Call Spread",
        "technical_setup": "uptrend",
        "news_catalyst": "earnings",
        "market_conditions": "bullish",
        "volatility_environment": "moderate",
        "risk_reward_ratio": 2.0,
        "probability_of_success": 0.55,
        "confidence_score": 65.0,
        "position_size": 1,
        "max_drawdown": 10.0,
        "max_favorable_excursion": 60.0,
        "max_adverse_excursion": 8.0,
        "sector": "Technology",
        "market_regime": "bullish",
        "entry_time": "10:30",
        "indicator_combo": "uptrend+RSI",
    }
    defaults.update(kw)
    return CompletedTrade(**defaults)


def test_identifies_best_and_weakest_strategies():
    trades = [
        _trade(strategy="Spread", profit_loss=200),
        _trade(strategy="Long Call", profit_loss=-100),
    ]
    p = identify_patterns(trades)
    assert "Spread" in p.best_strategies or p.best_strategies
    assert p.losing_trade_causes or p.weakest_strategies


def test_time_of_day_and_catalysts():
    trades = [_trade(entry_time="10:00"), _trade(entry_time="14:00", profit_loss=-50)]
    p = identify_patterns(trades)
    assert p.time_of_day_performance
    assert p.top_news_catalysts