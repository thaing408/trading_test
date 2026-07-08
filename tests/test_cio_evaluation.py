"""Unit tests for CIO evaluation framework."""

from trading_agent.cio.config import CIOConfig
from trading_agent.cio.evaluation import (
    build_scorecard,
    confirm_technical,
    evaluate_options_quality,
    evaluate_risk,
    validate_catalyst,
)
from trading_agent.cio.models import PhaseContext, TradeCandidate


def _candidate(**kw):
    defaults = {
        "symbol": "TEST",
        "direction": "Bullish",
        "strategy": "Debit Call Spread",
        "entry_price": 100.0,
        "strike_prices": [100.0, 105.0],
        "expiration": "2026-08-15",
        "profit_target": 108.0,
        "stop_loss": 97.0,
        "maximum_risk": 300.0,
        "maximum_reward": 700.0,
        "probability_of_success": 0.55,
        "confidence_score": 68.0,
        "primary_catalyst": "earnings beat",
        "catalyst_type": "earnings",
        "technical_summary": "uptrend",
        "technical_confirmations": ["trend:uptrend", "vwap:above", "macd:bullish", "rsi:55"],
        "options_summary": "good liquidity",
        "open_interest": 10000,
        "daily_options_volume": 30000,
        "bid_ask_spread_pct": 1.5,
        "iv_rank": 40.0,
        "expected_move_pct": 4.0,
        "probability_of_profit": 0.55,
        "liquidity_score": 80.0,
        "sector": "Technology",
    }
    defaults.update(kw)
    return TradeCandidate(**defaults)


def _context():
    return PhaseContext(
        overall_market_bias="Bullish",
        market_environment_score=65.0,
        market_regime="bullish",
    )


def test_validate_catalyst_rejects_speculation():
    c = _candidate(primary_catalyst="Reddit hype", catalyst_type="social_media")
    valid, notes, challenges = validate_catalyst(c)
    assert valid is False
    assert "Speculative" in notes or challenges


def test_technical_requires_min_confirmations():
    c = _candidate(technical_confirmations=["trend:uptrend", "macd:bullish"])
    passed, count, _, challenges = confirm_technical(c, CIOConfig(min_technical_confirmations=3))
    assert passed is False
    assert count == 2


def test_options_quality_rejects_thin_liquidity():
    c = _candidate(open_interest=100, daily_options_volume=200, liquidity_score=20.0, bid_ask_spread_pct=8.0)
    passed, _, challenges = evaluate_options_quality(c, CIOConfig())
    assert passed is False


def test_risk_requires_min_rr():
    c = _candidate(maximum_risk=500, maximum_reward=500)
    passed, rr, _, challenges = evaluate_risk(c, CIOConfig(min_risk_reward=2.0), 68.0)
    assert passed is False
    assert rr == 1.0


def test_build_scorecard_passes_strong_candidate():
    scorecard = build_scorecard(_candidate(), _context(), CIOConfig(), 68.0)
    assert scorecard.catalyst_valid
    assert scorecard.technical_pass
    assert scorecard.options_pass
    assert scorecard.risk_pass