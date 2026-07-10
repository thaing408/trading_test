"""Unit tests for stay-in-cash fallback when all candidates fail risk checks."""

from trading_agent.analysis.options import compute_options_metrics
from trading_agent.analysis.technical import compute_technical_analysis
from trading_agent.config import AgentConfig, RiskConfig
from trading_agent.models import ScreenerCandidate
from trading_agent.pipeline import run_pipeline
from trading_agent.ranking.ranker import build_opportunities
from trading_agent.reporter.plan import render_daily_plan
from trading_agent.risk.manager import evaluate_risk


def test_all_fail_risk_recommends_cash():
    """When every candidate fails risk checks, pipeline emits stay-in-cash."""
    config = AgentConfig(fixture_mode=True, use_live_data=False)
    config.risk = RiskConfig(
        min_volume=999_999_999,
        min_confidence_score=99.0,
    )
    plan = run_pipeline(config)
    report = render_daily_plan(plan)

    assert plan.stay_in_cash is True
    assert len(plan.ranked_opportunities) == 0
    assert "STAY IN CASH" in report
    assert plan.cash_recommendation_reason


def test_build_opportunities_empty_on_strict_confidence():
    closes = [100 + i for i in range(60)]
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    volumes = [1_000_000] * 60
    technical = compute_technical_analysis("X", closes, highs, lows, volumes)
    candidate = ScreenerCandidate(
        symbol="X",
        price=closes[-1],
        volume=5_000_000,
        relative_volume=2.2,
        options_liquidity_score=80.0,
        open_interest=5000,
        bid_ask_spread_pct=1.0,
        avg_daily_volume=4_000_000,
        market_cap=50_000_000_000,
        institutional_score=70.0,
    )
    options = compute_options_metrics(
        symbol="X",
        price=closes[-1],
        iv=30.0,
        iv_history=[25, 28, 30, 32, 27],
        strike=closes[-1] * 1.02,
        days_to_expiry=30,
        open_interest=5000,
        relative_volume=1.5,
        bid_ask_spread_pct=1.0,
        trend=technical.trend,
    )
    opps = build_opportunities(
        [(candidate, technical, options)],
        RiskConfig(min_confidence_score=99.0),
    )
    assert opps == []


def test_evaluate_risk_rejects_all_weak_candidates():
    weak = ScreenerCandidate(
        symbol="WEAK",
        price=5.0,
        volume=100,
        relative_volume=0.5,
        options_liquidity_score=10.0,
        open_interest=10,
        bid_ask_spread_pct=15.0,
    )
    closes = [5.0] * 10
    technical = compute_technical_analysis("WEAK", closes, closes, closes, [100] * 10)
    options = compute_options_metrics(
        symbol="WEAK",
        price=5.0,
        iv=80.0,
        iv_history=[70, 75, 80, 85, 78],
        strike=5.0,
        days_to_expiry=30,
        open_interest=10,
        relative_volume=0.5,
        bid_ask_spread_pct=15.0,
        trend="sideways",
    )
    qualified, rejected = evaluate_risk([(weak, technical, options)], RiskConfig())
    assert qualified == []
    assert len(rejected) == 1