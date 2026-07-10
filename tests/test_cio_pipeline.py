"""Unit tests for CIO pipeline and report."""

from trading_agent.cio.config import CIOConfig
from trading_agent.cio.pipeline import run_cio_pipeline
from trading_agent.cio.reporter import render_cio_report

REQUIRED_SECTIONS = [
    "## Daily Portfolio Summary",
    "## Governance Notes",
    "## Approved Trades",
    "## Modified Trades",
    "## Rejected Trades",
    "## Rejected / Delayed / Watchlist",
    "## Cross-Phase Context",
]

REQUIRED_APPROVED_FIELDS = [
    "Direction",
    "Strategy",
    "Entry Price",
    "Strike Prices",
    "Expiration",
    "Position Size",
    "Dollar Allocation",
    "Maximum Risk",
    "Maximum Reward",
    "Profit Target",
    "Stop Loss",
    "Exit Criteria",
    "Probability of Success",
    "Confidence Score",
    "Risk Rating",
    "Primary Catalyst",
    "Technical Summary",
    "Options Summary",
    "Key Risks",
    "Contingency Plan",
    "Why should this trade work?",
    "Why could this trade fail?",
    "What event would invalidate this thesis?",
    "Would a professional hedge fund approve this trade?",
    "Reward-to-Risk",
    "Capital Efficiency",
]

REQUIRED_SUMMARY_FIELDS = [
    "Overall Market Bias",
    "Market Environment Score",
    "Capital Allocation",
    "Cash Allocation",
    "Approved Trades",
    "Modified Trades",
    "Portfolio Risk Rating",
    "Overall Portfolio Risk",
]


def test_cio_report_structure():
    config = CIOConfig(fixture_mode=True, portfolio_value=100_000)
    report = run_cio_pipeline(config)
    text = render_cio_report(report)

    for section in REQUIRED_SECTIONS:
        assert section in text, f"Missing {section}"

    for field in REQUIRED_SUMMARY_FIELDS:
        assert field in text, f"Missing summary field {field}"

    book = report.approved + report.modified
    assert book, "expected at least one approved or modified trade in fixture"
    for field in REQUIRED_APPROVED_FIELDS:
        assert field in text, f"Missing approved field {field}"


def test_portfolio_allocation_and_diversification():
    config = CIOConfig(fixture_mode=True, portfolio_value=100_000)
    report = run_cio_pipeline(config)
    book = report.approved + report.modified
    total_pct = sum(t.position_size_pct for t in book)
    assert total_pct <= 80.0
    assert report.portfolio.cash_allocation_pct >= 20.0
    for t in book:
        assert t.dollar_allocation > 0
        assert t.position_size_pct <= config.max_single_position_pct
    assert report.portfolio.overall_portfolio_risk
    assert report.portfolio.correlation_note


def test_rejections_have_explanations():
    config = CIOConfig(fixture_mode=True)
    report = run_cio_pipeline(config)
    assert report.rejected
    for r in report.rejected:
        assert r.decision in ("Reject", "Delay", "Watchlist Only")
        assert r.explanation


def test_conviction_ranking_order():
    config = CIOConfig(fixture_mode=True, portfolio_value=100_000)
    report = run_cio_pipeline(config)
    book = report.approved + report.modified
    scores = [t.conviction_score for t in book]
    assert scores == sorted(scores, reverse=True)