"""Unit tests for strategy selection."""

from trading_agent.analysis.options import compute_options_metrics
from trading_agent.analysis.technical import compute_technical_analysis
from trading_agent.strategy.selector import select_strategy


def _setup(trend_slope=2):
    closes = [100 + i * trend_slope for i in range(60)]
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    volumes = [1_000_000] * 60
    technical = compute_technical_analysis("TEST", closes, highs, lows, volumes)
    iv_hist = [60, 62, 65, 63, 61] if trend_slope > 0 else [20, 22, 25, 23, 21]
    iv = 65 if trend_slope > 0 else 22
    options = compute_options_metrics(
        symbol="TEST",
        price=closes[-1],
        iv=iv,
        iv_history=iv_hist,
        strike=closes[-1] * 1.02,
        days_to_expiry=30,
        open_interest=5000,
        relative_volume=1.5,
        bid_ask_spread_pct=1.0,
        trend=technical.trend,
    )
    return technical, options, closes[-1]


def test_high_iv_bullish_selects_covered_call():
    technical, options, price = _setup(trend_slope=2)
    strategy = select_strategy(technical, options, price)
    assert strategy.name == "Covered Call"
    assert len(strategy.strike_prices) >= 1


def test_low_iv_bullish_selects_debit_call_spread():
    closes = [100 + i * 0.5 for i in range(60)]
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    volumes = [1_000_000] * 60
    technical = compute_technical_analysis("TEST", closes, highs, lows, volumes)
    options = compute_options_metrics(
        symbol="TEST",
        price=closes[-1],
        iv=22,
        iv_history=[20, 22, 25, 23, 21],
        strike=closes[-1] * 1.02,
        days_to_expiry=30,
        open_interest=5000,
        relative_volume=1.5,
        bid_ask_spread_pct=1.0,
        trend=technical.trend,
    )
    strategy = select_strategy(technical, options, closes[-1])
    assert "Spread" in strategy.name or strategy.name == "Long Call"


def test_bearish_high_iv_selects_cash_secured_put():
    closes = [200 - i * 2 for i in range(60)]
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    volumes = [1_000_000] * 60
    technical = compute_technical_analysis("TEST", closes, highs, lows, volumes)
    options = compute_options_metrics(
        symbol="TEST",
        price=closes[-1],
        iv=65,
        iv_history=[60, 62, 65, 63, 61],
        strike=closes[-1] * 0.98,
        days_to_expiry=30,
        open_interest=5000,
        relative_volume=1.5,
        bid_ask_spread_pct=1.0,
        trend=technical.trend,
    )
    strategy = select_strategy(technical, options, closes[-1])
    assert strategy.name in ("Cash Secured Put", "Long Put", "Debit Put Spread")