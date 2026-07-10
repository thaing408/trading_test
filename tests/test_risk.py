"""Unit tests for risk management gate."""

from trading_agent.analysis.options import compute_options_metrics
from trading_agent.analysis.technical import compute_technical_analysis
from trading_agent.config import RiskConfig
from trading_agent.models import ScreenerCandidate
from trading_agent.risk.manager import evaluate_risk, passes_risk_checks


def _make_candidate(**overrides):
    defaults = {
        "symbol": "TEST",
        "price": 100.0,
        "volume": 5_000_000,
        "relative_volume": 2.2,
        "options_liquidity_score": 70.0,
        "open_interest": 5000,
        "bid_ask_spread_pct": 1.0,
        "avg_daily_volume": 4_000_000,
        "market_cap": 50_000_000_000,
        "institutional_score": 65.0,
        "options_volume": 10_000,
    }
    defaults.update(overrides)
    return ScreenerCandidate(**defaults)


def _make_analysis(trend="uptrend"):
    closes = [100 + i for i in range(60)]
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    volumes = [1_000_000] * 60
    return compute_technical_analysis("TEST", closes, highs, lows, volumes)


def _make_options(trend="uptrend"):
    return compute_options_metrics(
        symbol="TEST",
        price=100.0,
        iv=30.0,
        iv_history=[25, 28, 30, 32, 27],
        strike=102.0,
        days_to_expiry=30,
        open_interest=5000,
        relative_volume=1.5,
        bid_ask_spread_pct=1.0,
        trend=trend,
    )


def test_passes_risk_checks_valid_setup():
    result = passes_risk_checks(
        _make_candidate(), _make_analysis(), _make_options(), RiskConfig()
    )
    assert result.passed is True
    assert result.reasons == []


def test_rejects_low_volume():
    result = passes_risk_checks(
        _make_candidate(volume=1000, avg_daily_volume=1000),
        _make_analysis(),
        _make_options(),
        RiskConfig(),
    )
    assert result.passed is False
    assert any("volume" in r.lower() or "Volume" in r for r in result.reasons)


def test_rejects_low_relative_volume_and_price():
    result = passes_risk_checks(
        _make_candidate(relative_volume=1.0, price=15.0),
        _make_analysis(),
        _make_options(),
        RiskConfig(),
    )
    assert result.passed is False
    assert any("Relative volume" in r for r in result.reasons)
    assert any("Price" in r for r in result.reasons)


def test_rejects_unknown_market_cap():
    result = passes_risk_checks(
        _make_candidate(market_cap=0),
        _make_analysis(),
        _make_options(),
        RiskConfig(),
    )
    assert result.passed is False
    assert any("Market cap" in r for r in result.reasons)


def test_rejects_wide_spread():
    result = passes_risk_checks(
        _make_candidate(bid_ask_spread_pct=10.0),
        _make_analysis(),
        _make_options(),
        RiskConfig(),
    )
    assert result.passed is False
    assert any("spread" in r.lower() for r in result.reasons)


def test_evaluate_risk_splits_qualified_and_rejected():
    good = (_make_candidate(symbol="GOOD"), _make_analysis(), _make_options())
    bad = (
        _make_candidate(symbol="BAD", volume=100, avg_daily_volume=100, relative_volume=0.5),
        _make_analysis(),
        _make_options(),
    )
    qualified, rejected = evaluate_risk([good, bad], RiskConfig())
    assert len(qualified) == 1
    assert qualified[0][0].symbol == "GOOD"
    assert len(rejected) == 1
    assert rejected[0].symbol == "BAD"