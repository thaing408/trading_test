"""Unit tests for options metrics."""

from trading_agent.analysis.options import (
    compute_options_metrics,
    expected_move_pct,
    iv_percentile,
    iv_rank,
    probability_of_profit,
)


def test_iv_rank_midpoint():
    assert iv_rank(25, [20, 30]) == 50.0


def test_iv_percentile():
    assert iv_percentile(25, [20, 22, 24, 26, 28]) == 60.0


def test_expected_move_positive():
    assert expected_move_pct(100, 30, 30) > 0


def test_probability_of_profit_range():
    pop = probability_of_profit(0.6, "bullish")
    assert 0.35 <= pop <= 0.85


def test_compute_options_metrics_fields():
    metrics = compute_options_metrics(
        symbol="TEST",
        price=100.0,
        iv=30.0,
        iv_history=[25, 28, 30, 32, 27],
        strike=102.0,
        days_to_expiry=30,
        open_interest=5000,
        relative_volume=2.2,
        bid_ask_spread_pct=1.0,
        trend="uptrend",
        options_volume=8000,
    )
    assert metrics.symbol == "TEST"
    assert metrics.implied_volatility == 30.0
    assert 0 <= metrics.iv_rank <= 100
    assert metrics.unusual_activity is True
    assert metrics.probability_of_profit > 0
    assert 0.15 <= metrics.probability_of_touch <= 0.95
    assert metrics.options_volume == 8000
    assert metrics.open_interest == 5000