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
    assert "NATGAS" in snapshot.commodities or "COPPER" in snapshot.commodities
    assert snapshot.etfs
    for etf in ("SPY", "QQQ", "IWM", "DIA", "XLK", "SMH", "SOXX", "XLF", "XLE", "XBI"):
        assert etf in snapshot.etfs
    assert snapshot.treasury_yields
    assert snapshot.breadth
    assert any(
        isinstance(v, dict) and v.get("status") == "unavailable"
        for v in snapshot.breadth.values()
    )
    assert "MOVE" in snapshot.unavailable or snapshot.unavailable


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


def test_quote_summary_rejects_non_finite_prices(monkeypatch):
    """yfinance NaN closes must not enter the snapshot as change_pct=NaN."""
    import math

    import pandas as pd

    from trading_agent.collectors import market as market_mod

    class FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, period="5d", interval="1d"):
            return pd.DataFrame({"Close": [float("nan"), float("nan")]})

    monkeypatch.setattr(market_mod, "yfinance", None, raising=False)

    def fake_import_yf():
        raise AssertionError("should use injected FakeTicker path")

    # Patch yfinance.Ticker used inside _quote_summary
    import types
    import sys

    fake_yf = types.SimpleNamespace(Ticker=FakeTicker)
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)

    try:
        market_mod._quote_summary("ES=F")
        assert False, "expected ValueError for non-finite prices"
    except ValueError as exc:
        assert "Non-finite" in str(exc) or "non-finite" in str(exc).lower()

    # Finite path still works
    class OkTicker:
        def history(self, period="5d", interval="1d"):
            return pd.DataFrame({"Close": [100.0, 101.0]})

    fake_yf.Ticker = lambda symbol: OkTicker()
    quote = market_mod._quote_summary("ES=F")
    assert quote["last"] == 101.0
    assert quote["change_pct"] == 1.0
    assert math.isfinite(quote["change_pct"])