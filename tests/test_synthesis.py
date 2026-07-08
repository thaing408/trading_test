"""Unit tests for market/calendar/news synthesis."""

from trading_agent.collectors.base import load_fixture
from trading_agent.collectors.calendar import collect_economic_calendar
from trading_agent.collectors.market import collect_market_snapshot
from trading_agent.collectors.news import collect_news_catalysts
from trading_agent.config import AgentConfig
from trading_agent.models import CalendarEvent, EconomicCalendar, NewsCatalysts, NewsItem, ScreenerCandidate
from trading_agent.synthesis.market_context import build_watchlist, synthesize_market_context


def _fixture_context():
    config = AgentConfig(fixture_mode=True, use_live_data=False)
    market = collect_market_snapshot(config)
    calendar = collect_economic_calendar(config)
    news = collect_news_catalysts(config, ["NVDA", "AAPL"])
    return synthesize_market_context(market, calendar, news)


def test_synthesis_uses_all_market_groups():
    ctx = _fixture_context()
    for key in ("futures", "international", "bonds", "dxy", "commodities", "crypto"):
        assert key in ctx.overnight_summary, f"missing overnight synthesis for {key}"
    assert ctx.environment_score != 50.0


def test_calendar_affects_score_and_bias():
    config = AgentConfig(fixture_mode=True)
    market = collect_market_snapshot(config)
    high_cal = EconomicCalendar(
        source="test",
        events=[CalendarEvent(time="08:30", event="CPI Release", impact="high")],
    )
    low_cal = EconomicCalendar(source="test", events=[])
    news = NewsCatalysts(source="test", items=[])
    high_ctx = synthesize_market_context(market, high_cal, news)
    low_ctx = synthesize_market_context(market, low_cal, news)
    assert high_ctx.environment_score < low_ctx.environment_score
    assert "calendar risk" in high_ctx.bias.lower()
    assert high_ctx.high_impact_events


def test_news_boosts_watchlist_and_bias():
    config = AgentConfig(fixture_mode=True)
    market = collect_market_snapshot(config)
    calendar = collect_economic_calendar(config)
    news = collect_news_catalysts(config, ["NVDA", "AAPL"])
    ctx = synthesize_market_context(market, calendar, news)
    assert ctx.news_highlights
    assert "NVDA" in ctx.catalyst_symbols
    assert "active catalyst" in ctx.bias.lower()

    candidates = [
        ScreenerCandidate("XLF", 42, 2_000_000, 0.9, 60, 3000, 3.5),
        ScreenerCandidate("NVDA", 130, 45_000_000, 1.8, 85, 15000, 1.2),
    ]
    watchlist = build_watchlist(candidates, ctx, limit=2)
    assert watchlist[0] == "NVDA"


def test_pipeline_research_summary_includes_synthesis():
    from trading_agent.pipeline import run_pipeline

    plan = run_pipeline(AgentConfig(fixture_mode=True, use_live_data=False))
    rs = plan.research_summary
    assert rs.get("calendar_summary")
    assert rs.get("news_highlights")
    assert rs.get("overnight_summary")
    assert rs.get("market_signals")