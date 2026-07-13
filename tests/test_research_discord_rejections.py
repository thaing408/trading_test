"""Discord-facing research messages: scanned count + rejection reasons."""

from __future__ import annotations

from trading_agent.config import AgentConfig
from trading_agent.models import DailyTradingPlan, RejectedSetup, TradeOpportunity
from trading_agent.pipeline import run_pipeline
from trading_agent.reporter.plan import render_daily_plan
from trading_agent.session.play_formatter import (
    format_premarket_plays,
    format_rejection_summary,
    format_research_plays,
)


def _minimal_plan(
    *,
    stay_in_cash: bool,
    screened: int,
    rejections: list[RejectedSetup],
    opportunities: list | None = None,
) -> DailyTradingPlan:
    return DailyTradingPlan(
        date="2026-07-13",
        overall_market_bias="Neutral",
        market_environment_score=50.0,
        top_watchlist=["NVDA", "AAPL"],
        ranked_opportunities=opportunities or [],
        rejection_reasons=rejections,
        research_summary={
            "candidates_screened": screened,
            "qualified_count": 0 if stay_in_cash else len(opportunities or []),
            "news_highlights": [],
            "top_candidates_cap": 3,
        },
        stay_in_cash=stay_in_cash,
        cash_recommendation_reason="Test cash reason",
    )


def test_cash_path_shows_scanned_and_rejection_counts_and_reasons():
    rejects = [
        RejectedSetup("AAA", "Relative volume too low"),
        RejectedSetup("BBB", "Bid-ask spread too wide"),
        RejectedSetup("CCC", "Technical score weak"),
    ]
    plan = _minimal_plan(stay_in_cash=True, screened=12, rejections=rejects)
    text = format_research_plays(plan)
    assert "Scanned:** 12" in text or "scanned **12**" in text
    assert "rejected **3**" in text
    assert "showing **3**" in text
    assert "AAA" in text and "Relative volume too low" in text
    assert "BBB" in text and "CCC" in text
    assert "STAY IN CASH" in text


def test_non_cash_path_still_shows_rejections():
    """Approvals and rejections both visible when opportunities exist."""
    rejects = [RejectedSetup("ZZZ", "Open interest below minimum")]
    # Minimal fake opportunity: only fields formatter reads for header path
    # Ranked list non-empty so stay_in_cash is False path
    from dataclasses import fields
    from trading_agent.models import OptionsMetrics, TechnicalAnalysis

    tech = TechnicalAnalysis(
        symbol="NVDA",
        trend="uptrend",
        rsi=55.0,
        macd_signal="bullish",
        adx=25.0,
        atr=2.0,
        bollinger_position="middle",
        support=100.0,
        resistance=120.0,
        relative_strength=1.0,
        vwap_relation="above",
        ma_alignment="bullish",
        volume_profile_bias="neutral",
        score=70.0,
    )
    opts = OptionsMetrics(
        symbol="NVDA",
        implied_volatility=30.0,
        iv_rank=40.0,
        iv_percentile=50.0,
        expected_move_pct=3.0,
        delta=0.5,
        gamma=0.01,
        theta=-0.05,
        vega=0.1,
        unusual_activity=False,
        institutional_flow_bias="bullish",
        liquidity_score=80.0,
        probability_of_profit=0.55,
    )
    opp = TradeOpportunity(
        rank=1,
        symbol="NVDA",
        strategy="Long Call",
        entry_price=130.0,
        strike_prices=[135.0],
        expiration="2026-08-15",
        profit_target=140.0,
        stop_loss=125.0,
        maximum_risk=500.0,
        maximum_reward=1000.0,
        probability_of_success=0.55,
        confidence_score=70.0,
        supporting_reasons=["test"],
        technical=tech,
        options=opts,
        direction="Bullish",
    )
    plan = _minimal_plan(
        stay_in_cash=False,
        screened=10,
        rejections=rejects,
        opportunities=[opp],
    )
    text = format_premarket_plays(plan)
    assert "NVDA" in text
    assert "scanned **10**" in text or "Scanned:** 10" in text
    assert "rejected **1**" in text
    assert "ZZZ" in text and "Open interest" in text
    assert "STAY IN CASH" not in text


def test_truncation_reports_total_vs_shown():
    rejects = [RejectedSetup(f"S{i}", f"reason {i}") for i in range(12)]
    plan = _minimal_plan(stay_in_cash=True, screened=12, rejections=rejects)
    block = "\n".join(format_rejection_summary(plan, max_shown=8))
    assert "rejected **12**" in block
    assert "showing **8**" in block
    assert "more rejection" in block.lower()
    assert "S0" in block and "S7" in block
    assert "S11" not in block  # beyond display cap


def test_zero_scanned_still_emits_count():
    plan = _minimal_plan(stay_in_cash=True, screened=0, rejections=[])
    text = format_research_plays(plan)
    assert "Scanned:** 0" in text or "scanned **0**" in text
    assert "rejected **0**" in text


def test_fixture_pipeline_discord_path_has_scan_and_rejects():
    plan = run_pipeline(AgentConfig(fixture_mode=True, use_live_data=False))
    text = format_research_plays(plan)
    screened = int(plan.research_summary.get("candidates_screened", 0))
    assert f"Scanned:** {screened}" in text or f"scanned **{screened}**" in text
    n_rej = len(plan.rejection_reasons)
    assert f"rejected **{n_rej}**" in text
    report = render_daily_plan(plan)
    assert "Scan summary" in report or "Candidates screened" in report
    assert f"Rejected (with reasons): {n_rej}" in report or "rejected" in report.lower()
