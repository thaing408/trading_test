"""Unit tests for Roll and Enter action paths."""

from datetime import datetime, timezone

from trading_agent.intraday.config import IntradayConfig, IntradayRiskConfig
from trading_agent.intraday.decisions.evaluator import evaluate_position
from trading_agent.intraday.decisions.guards import days_to_expiration
from trading_agent.intraday.models import (
    OpenPosition,
    SessionSnapshot,
    SessionSynthesis,
    SymbolSessionData,
)
from trading_agent.intraday.pipeline import run_intraday_pipeline


def _sym_data(**kw):
    defaults = {
        "symbol": "NVDA",
        "price": 130.0,
        "change_pct": 0.5,
        "vwap": 129.0,
        "volume": 5_000_000,
        "relative_volume": 1.2,
        "support": 128.0,
        "resistance": 135.0,
        "trend": "uptrend",
        "momentum": "steady",
        "iv": 40.0,
        "iv_change_pct": 1.0,
        "open_interest": 10000,
        "oi_change_pct": 1.0,
        "delta": 0.55,
        "gamma": 0.02,
        "theta": -0.07,
        "vega": 0.14,
        "options_flow_bias": "bullish",
    }
    defaults.update(kw)
    return SymbolSessionData(**defaults)


def _snapshot(symbol="NVDA", sym=None):
    sym = sym or _sym_data(symbol=symbol)
    return SessionSnapshot(
        source="test",
        market_regime="bullish",
        prior_regime="bullish",
        vix=16.0,
        vix_change_pct=0.0,
        breadth_advancers=5,
        breadth_decliners=3,
        breadth_ratio=0.6,
        sector_leaders=["XLK"],
        sector_laggards=["XLE"],
        symbols={symbol: sym},
        breaking_news=[],
        economic_announcements=[],
    )


def _synthesis():
    return SessionSynthesis(
        regime_shift=False,
        regime_description="bullish",
        observations=[],
        risk_environment="normal",
        session_score=60.0,
    )


def test_roll_when_near_expiration():
    pos = OpenPosition(
        symbol="NVDA",
        strategy="Debit Call Spread",
        entry_price=130.0,
        stop_loss=125.0,
        profit_target=140.0,
        strike_prices=[130.0, 135.0],
        expiration="2026-07-11",
        original_probability=0.55,
        original_confidence=68.0,
    )
    rec = evaluate_position(pos, _snapshot(), _synthesis(), IntradayRiskConfig(roll_days_threshold=14))
    assert rec.action == "Roll"
    assert "expiration" in rec.what_changed.lower()


def test_enter_for_pending_entry():
    pos = OpenPosition(
        symbol="AMD",
        strategy="Long Call",
        entry_price=160.0,
        stop_loss=155.0,
        profit_target=175.0,
        strike_prices=[165.0],
        expiration="2026-08-15",
        pending_entry=True,
        original_probability=0.5,
        original_confidence=60.0,
    )
    snap = _snapshot(
        "AMD",
        _sym_data(symbol="AMD", price=162.0, vwap=161.0, trend="uptrend"),
    )
    rec = evaluate_position(pos, snap, _synthesis(), IntradayRiskConfig())
    assert rec.action == "Enter"


def test_days_to_expiration_uses_position_field():
    dte = days_to_expiration("2026-07-11", datetime(2026, 7, 8, tzinfo=timezone.utc))
    assert dte == 3


def test_portfolio_risk_emitted_as_notification():
    config = IntradayConfig(fixture_mode=True, use_live_data=False)
    config.risk.max_portfolio_risk_pct = 1.0
    report = run_intraday_pipeline(config)
    portfolio_alerts = [n for n in report.notifications if n.symbol == "PORTFOLIO"]
    assert portfolio_alerts
    assert any("Portfolio aggregate" in n.message for n in portfolio_alerts)