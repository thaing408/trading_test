"""Unit tests for data collectors (fixture mode)."""

from trading_agent.config import AgentConfig
from trading_agent.collectors import (
    collect_economic_calendar,
    collect_market_snapshot,
    collect_news_catalysts,
    collect_screener_candidates,
)


def test_market_collector_fixture():
    config = AgentConfig(fixture_mode=True, use_live_data=False)
    snapshot = collect_market_snapshot(config)
    assert snapshot.source == "fixture"
    assert snapshot.futures
    assert snapshot.vix
    assert snapshot.sector_rotation


def test_calendar_collector_fixture():
    config = AgentConfig(fixture_mode=True, use_live_data=False)
    cal = collect_economic_calendar(config)
    assert cal.source == "fixture"
    assert len(cal.events) >= 1


def test_news_collector_fixture():
    config = AgentConfig(fixture_mode=True, use_live_data=False)
    news = collect_news_catalysts(config, ["NVDA", "AAPL"])
    assert news.source == "fixture"
    assert len(news.items) >= 1


def test_screener_collector_fixture():
    config = AgentConfig(fixture_mode=True, use_live_data=False)
    screener = collect_screener_candidates(config)
    assert screener.source == "fixture"
    assert len(screener.candidates) >= 1
    c = screener.candidates[0]
    assert c.price > 0
    assert c.volume > 0