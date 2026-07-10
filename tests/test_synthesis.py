"""Unit tests for market/calendar/news synthesis."""

from trading_agent.collectors.calendar import collect_economic_calendar
from trading_agent.collectors.market import collect_market_snapshot
from trading_agent.collectors.news import collect_news_catalysts
from trading_agent.config import AgentConfig
from trading_agent.models import (
    CalendarEvent,
    EconomicCalendar,
    MarketSnapshot,
    NewsCatalysts,
    NewsItem,
    ScreenerCandidate,
)
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
    assert ctx.sector_ranking
    assert ctx.etf_snapshot
    assert ctx.outlook in ("Bullish", "Bearish", "Neutral")
    assert ctx.top_opportunities
    assert ctx.major_risks
    assert ctx.expected_drivers
    assert ctx.market_posture
    assert ctx.vix_term_note or "VIX" in str(ctx.overnight_summary)


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


def test_live_unavailable_calendar_and_news_omitted_from_bias():
    """Fixture-fallback / unavailable must never invent Jobless Claims or fake NVDA headlines."""
    market = collect_market_snapshot(AgentConfig(fixture_mode=True))
    cal = EconomicCalendar(
        source="unavailable",
        events=[CalendarEvent(time="08:30 ET", event="Initial Jobless Claims", impact="high")],
        errors=["FMP_API_KEY not set"],
    )
    news = NewsCatalysts(
        source="fixture-fallback",
        items=[
            NewsItem(
                symbol="NVDA",
                headline="NVDA beats earnings estimates, raises guidance",
                source="fixture",
                category="earnings",
            )
        ],
    )
    ctx = synthesize_market_context(market, cal, news)
    assert "Jobless Claims" not in ctx.bias
    assert "NVDA beats" not in ctx.bias
    assert "calendar risk" not in ctx.bias.lower()
    assert "active catalyst" not in ctx.bias.lower()
    assert ctx.high_impact_events == []
    assert ctx.news_highlights == []


def test_live_collectors_do_not_fill_fixture_events():
    cfg = AgentConfig(fixture_mode=False, use_live_data=True)
    cal = collect_economic_calendar(cfg)
    news = collect_news_catalysts(cfg, ["NVDA", "AAPL"])
    # Without FMP / empty yfinance news: empty + unavailable (never fixture-fallback content)
    if cal.source not in ("fmp", "fmp-earnings"):
        assert cal.source == "unavailable"
        assert cal.events == []
    if news.source != "yfinance":
        assert news.source == "unavailable"
        assert news.items == []


def test_breadth_and_move_unavailable_marked_not_fabricated():
    snap = MarketSnapshot(
        source="test",
        futures={"ES": {"change_pct": -0.8, "last": 5400}},
        international={"NIKKEI": {"change_pct": -1.0}},
        bonds={"TLT": {"change_pct": 0.5}},
        dollar_index={"DXY": {"change_pct": 0.4}},
        vix={"VIX": {"last": 28.0, "change_pct": 8.0}},
        commodities={"GOLD": {"change_pct": 1.0}, "OIL": {"change_pct": -1.0}},
        crypto={"BTC": {"change_pct": -2.0}, "ETH": {"change_pct": -1.5}},
        sector_rotation={
            "XLU": {"change_pct": 0.8},
            "XLP": {"change_pct": 0.6},
            "XLK": {"change_pct": -0.9},
            "XLE": {"change_pct": -1.2},
        },
        etfs={"SPY": {"change_pct": -0.7, "last": 540}},
        breadth={
            "TRIN": {"status": "unavailable", "note": "no feed"},
            "TICK": {"status": "unavailable", "note": "no feed"},
        },
        unavailable={"MOVE": "no feed", "CME_FEDWATCH": "no feed"},
    )
    cal = EconomicCalendar(source="unavailable", events=[], errors=["no key"])
    news = NewsCatalysts(source="unavailable", items=[])
    ctx = synthesize_market_context(snap, cal, news)
    assert any("unavailable" in n.lower() for n in ctx.breadth_notes)
    assert "MOVE" in ctx.unavailable_series
    assert "Jobless Claims" not in ctx.bias
    assert "NVDA" not in ctx.bias
    assert ctx.outlook in ("Bullish", "Bearish", "Neutral")
    # Risk-off-ish inputs should not score as bullish risk-on
    assert ctx.environment_score < 55
    assert ctx.outlook in ("Bearish", "Neutral")


def test_risk_on_fixture_scores_higher_than_risk_off_construct():
    risk_on = _fixture_context()
    risk_off_snap = MarketSnapshot(
        source="test",
        futures={"ES": {"change_pct": -1.2, "last": 5300}, "NQ": {"change_pct": -1.5, "last": 19000}},
        international={
            "NIKKEI": {"change_pct": -1.5},
            "FTSE": {"change_pct": -1.0},
            "DAX": {"change_pct": -1.1},
        },
        bonds={"TLT": {"change_pct": 1.0}},
        dollar_index={"DXY": {"change_pct": 0.6}},
        vix={"VIX": {"last": 32.0, "change_pct": 12.0}},
        commodities={"GOLD": {"change_pct": 1.5}, "OIL": {"change_pct": -2.0}},
        crypto={"BTC": {"change_pct": -3.0}, "ETH": {"change_pct": -2.5}},
        sector_rotation={
            "XLU": {"change_pct": 1.0},
            "XLP": {"change_pct": 0.8},
            "XLK": {"change_pct": -1.5},
            "XLY": {"change_pct": -1.2},
            "XLE": {"change_pct": -0.5},
        },
        etfs={
            "SPY": {"change_pct": -1.0, "last": 530},
            "QQQ": {"change_pct": -1.4, "last": 460},
        },
        breadth={"TRIN": {"status": "unavailable", "note": "n/a"}},
        unavailable={"MOVE": "n/a"},
    )
    empty = EconomicCalendar(source="test", events=[])
    news = NewsCatalysts(source="test", items=[])
    risk_off = synthesize_market_context(risk_off_snap, empty, news)
    assert risk_on.environment_score > risk_off.environment_score
    assert risk_off.outlook in ("Bearish", "Neutral")
    assert risk_on.outlook in ("Bullish", "Neutral")


def test_high_impact_keywords_cover_macro_types():
    market = collect_market_snapshot(AgentConfig(fixture_mode=True))
    events = [
        CalendarEvent(time="08:30", event="CPI m/m", impact="medium"),
        CalendarEvent(time="08:30", event="PPI final demand", impact="medium"),
        CalendarEvent(time="08:30", event="GDP advance", impact="medium"),
        CalendarEvent(time="08:30", event="Nonfarm Payrolls", impact="medium"),
        CalendarEvent(time="13:00", event="Treasury Auction 10-Year", impact="medium"),
        CalendarEvent(time="14:00", event="Fed Speaker Williams", impact="medium"),
    ]
    cal = EconomicCalendar(source="test", events=events)
    ctx = synthesize_market_context(market, cal, NewsCatalysts(source="test", items=[]))
    joined = " ".join(ctx.high_impact_events).lower()
    assert "cpi" in joined
    assert "ppi" in joined
    assert "gdp" in joined
    assert "nonfarm" in joined or "payroll" in joined
    assert "auction" in joined
    assert "fed" in joined
    # MI risk flag only — never position-size / stop language
    assert "reduce size" not in ctx.calendar_summary.lower()
    assert "widen stops" not in ctx.calendar_summary.lower()
    assert "elevated event risk" in ctx.calendar_summary.lower()


def test_nan_change_pct_not_printed_as_nan_avg():
    """Non-finite change_pct must not produce '+nan%' in overnight Asia/International lines."""
    import math

    snap = MarketSnapshot(
        source="test",
        futures={"ES": {"change_pct": 0.2, "last": 5400}},
        international={
            "NIKKEI": {"change_pct": float("nan"), "last": 39000},
            "HSI": {"change_pct": float("nan"), "last": 17500},
            "FTSE": {"change_pct": float("nan"), "last": 8200},
            "DAX": {"change_pct": 0.3, "last": 18200},
        },
        bonds={"TLT": {"change_pct": 0.0}},
        dollar_index={"DXY": {"change_pct": 0.0}},
        vix={"VIX": {"last": 16.0, "change_pct": -1.0}},
        commodities={
            "GOLD": {"change_pct": 0.1},
            "SILVER": {"change_pct": 0.2},
            "OIL": {"change_pct": -0.1},
            "COPPER": {"change_pct": 0.0},
            "NATGAS": {"change_pct": 0.5},
        },
        crypto={"BTC": {"change_pct": float("nan")}, "ETH": {"change_pct": float("nan")}},
        sector_rotation={"XLK": {"change_pct": 0.2}},
        etfs={"SPY": {"change_pct": 0.1, "last": 500}},
    )
    ctx = synthesize_market_context(
        snap,
        EconomicCalendar(source="test", events=[]),
        NewsCatalysts(source="test", items=[]),
    )
    for key in ("asia", "international", "crypto", "commodities"):
        val = ctx.overnight_summary[key]
        assert "nan" not in val.lower(), f"{key} leaked nan: {val}"
    # Asia keys all nan -> unavailable; Europe has DAX finite
    assert ctx.overnight_summary["asia"] == "unavailable"
    assert "avg" in ctx.overnight_summary["europe"]
    assert "Silver" in ctx.overnight_summary["commodities"]
    # crypto all non-finite -> unavailable or no nan
    assert math.isnan is not None  # sanity
    assert "nan" not in ctx.overnight_summary["crypto"].lower()


def test_overnight_commodities_include_silver_oil_ng_gold_copper():
    ctx = _fixture_context()
    line = ctx.overnight_summary["commodities"].lower()
    for name in ("gold", "silver", "oil", "copper", "ng"):
        assert name in line, f"missing {name} in commodities overnight: {line}"
