"""Tests for Market Intelligence pass."""

from __future__ import annotations

from trading_agent.config import AgentConfig
from trading_agent.session.intelligence import run_intelligence_pass
from trading_agent.session.play_formatter import format_intelligence_brief


def test_intelligence_pass_fixture_has_bias_and_catalysts():
    config = AgentConfig(fixture_mode=True, use_live_data=False)
    brief = run_intelligence_pass(config)
    text = format_intelligence_brief(brief)

    assert brief.bias
    assert brief.environment_score > 0
    assert "Market Intelligence" in text
    assert brief.news_highlights or brief.market_signals