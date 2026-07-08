"""Unit tests for intraday pipeline and reporter."""

from trading_agent.intraday.config import IntradayConfig
from trading_agent.intraday.pipeline import run_intraday_pipeline
from trading_agent.intraday.reporter import render_intraday_report

REQUIRED_SECTIONS = [
    "## Session Observations",
    "## Risk Limit Evaluation",
    "## Position Recommendations",
    "## Plan Context",
]

REQUIRED_FIELDS = [
    "**What Changed:**",
    "**Why Recommended:**",
    "**Risk If No Action:**",
    "**Updated Probability of Success:**",
    "**Updated Confidence Score:**",
]


def test_intraday_report_structure():
    config = IntradayConfig(fixture_mode=True, use_live_data=False)
    report = run_intraday_pipeline(config)
    text = render_intraday_report(report)

    for section in REQUIRED_SECTIONS:
        assert section in text, f"Missing {section}"

    assert not report.no_open_positions
    for rec in report.recommendations:
        assert rec.action
        assert rec.what_changed
        assert rec.why_recommended
        assert rec.risk_if_no_action
        assert 0 < rec.updated_probability <= 1
        assert 0 <= rec.updated_confidence <= 100

    for field in REQUIRED_FIELDS:
        assert field in text, f"Missing {field}"


def test_session_synthesis_in_report():
    config = IntradayConfig(fixture_mode=True, use_live_data=False)
    report = run_intraday_pipeline(config)
    text = render_intraday_report(report)
    assert "VWAP" in text or "vwap" in text.lower() or "regime" in text.lower()
    assert report.session.observations
    assert len(report.session.observations) >= 3
    assert "Greeks" in text or "Δ=" in text


def test_notifications_present_for_triggers():
    config = IntradayConfig(fixture_mode=True, use_live_data=False)
    report = run_intraday_pipeline(config)
    assert len(report.notifications) >= 1
    text = render_intraday_report(report)
    assert "## Immediate Notifications" in text or report.notifications