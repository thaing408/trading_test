"""Unit tests for Hold / Take No Action paths."""

from trading_agent.intraday.config import IntradayConfig, IntradayRiskConfig
from trading_agent.intraday.decisions.evaluator import evaluate_position
from trading_agent.intraday.models import (
    OpenPosition,
    SessionSnapshot,
    SessionSynthesis,
    SymbolSessionData,
)
from trading_agent.intraday.pipeline import run_intraday_pipeline


def test_stable_position_receives_hold():
    pos = OpenPosition(
        symbol="NVDA",
        strategy="Debit Call Spread",
        entry_price=130.0,
        stop_loss=125.0,
        profit_target=140.0,
        strike_prices=[130.0, 135.0],
        expiration="2026-08-15",
        original_probability=0.55,
        original_confidence=68.0,
    )
    snap = SessionSnapshot(
        source="test",
        market_regime="bullish",
        prior_regime="bullish",
        vix=16.0,
        vix_change_pct=0.5,
        breadth_advancers=5,
        breadth_decliners=3,
        breadth_ratio=0.62,
        sector_leaders=["XLK"],
        sector_laggards=["XLE"],
        symbols={
            "NVDA": SymbolSessionData(
                symbol="NVDA",
                price=130.5,
                change_pct=0.2,
                vwap=131.5,
                volume=5_000_000,
                relative_volume=1.2,
                support=128.0,
                resistance=135.0,
                trend="uptrend",
                momentum="steady",
                iv=40.0,
                iv_change_pct=0.5,
                open_interest=10000,
                oi_change_pct=1.0,
                delta=0.55,
                gamma=0.02,
                theta=-0.07,
                vega=0.14,
                options_flow_bias="bullish",
            )
        },
        breaking_news=[],
        economic_announcements=[],
    )
    synth = SessionSynthesis(
        regime_shift=False,
        regime_description="Session regime is bullish",
        observations=["stable"],
        risk_environment="normal",
        session_score=62.0,
    )
    rec = evaluate_position(pos, snap, synth, IntradayRiskConfig())
    assert rec.action in ("Hold", "Take No Action")
    assert rec.why_recommended
    assert rec.risk_if_no_action


def test_fixture_pipeline_hold_or_stable_action():
    config = IntradayConfig(fixture_mode=True, use_live_data=False)
    report = run_intraday_pipeline(config)
    actions = {r.action for r in report.recommendations}
    assert len(report.recommendations) >= 1
    assert actions  # at least one evaluated action