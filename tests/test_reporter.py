"""Unit tests for Daily Trading Plan reporter."""

from trading_agent.config import AgentConfig
from trading_agent.pipeline import run_pipeline
from trading_agent.reporter.plan import render_daily_plan

REQUIRED_SECTIONS = [
    "## Overall Market Bias",
    "## Market Environment Score",
    "## Overnight Global Markets",
    "## Economic Calendar Highlights",
    "## News & Catalysts",
    "## Top Watchlist",
    "## Ranked Trade Opportunities",
    "## Rejected Lower-Quality Setups",
    "## Research Summary",
]

REQUIRED_TRADE_FIELDS = [
    "**Ticker:**",
    "**Direction:**",
    "**Trade Thesis:**",
    "**Entry Price:**",
    "**Strike Prices:**",
    "**Expiration:**",
    "**Profit Target:**",
    "**Stop Loss:**",
    "**Maximum Risk:**",
    "**Maximum Reward:**",
    "**Probability of Success:**",
    "**Confidence Score:**",
    "**Trade Quality Score:**",
    "**Risks:**",
    "**Supporting Reasons:**",
]


def test_fixture_plan_contains_all_sections():
    config = AgentConfig(fixture_mode=True, use_live_data=False)
    plan = run_pipeline(config)
    report = render_daily_plan(plan)

    for section in REQUIRED_SECTIONS:
        assert section in report, f"Missing section: {section}"

    assert plan.overall_market_bias
    assert 0 <= plan.market_environment_score <= 100
    assert plan.top_watchlist


def test_fixture_plan_trade_fields_when_opportunities_exist():
    config = AgentConfig(fixture_mode=True, use_live_data=False)
    config.risk.min_confidence_score = 40.0
    plan = run_pipeline(config)
    report = render_daily_plan(plan)

    if not plan.stay_in_cash:
        for field in REQUIRED_TRADE_FIELDS:
            assert field in report, f"Missing trade field: {field}"
        assert plan.ranked_opportunities[0].strategy


def test_fixture_plan_rejection_section_has_counts():
    plan = run_pipeline(AgentConfig(fixture_mode=True, use_live_data=False))
    report = render_daily_plan(plan)
    screened = plan.research_summary.get("candidates_screened", 0)
    assert f"scanned **{screened}**" in report or f"Candidates screened: {screened}" in report
    n_rej = len(plan.rejection_reasons)
    assert f"rejected **{n_rej}**" in report or f"Rejected (with reasons): {n_rej}" in report