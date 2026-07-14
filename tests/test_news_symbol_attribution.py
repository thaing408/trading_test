"""Headline→symbol attribution: no co-tagged sector noise (e.g. TSMC on AAPL)."""

from __future__ import annotations

from unittest.mock import patch

from trading_agent.collectors.news import (
    _fetch_yfinance_news,
    headline_mentions_symbol,
    mentioned_watch_symbols,
)


def test_headline_mentions_ticker_and_alias():
    assert headline_mentions_symbol("AAPL", "Apple raises iPhone outlook")
    assert headline_mentions_symbol("AAPL", "AAPL stock jumps after services beat")
    assert headline_mentions_symbol("AAPL", "$AAPL hits record high")
    assert headline_mentions_symbol("NVDA", "NVIDIA expands AI chip capacity")
    assert not headline_mentions_symbol("AAPL", "TSMC posts record revenue on AI demand")
    assert not headline_mentions_symbol("AAPL", "Why TSMC’s Record Revenue Isn’t Reviving the AI Trade")
    assert headline_mentions_symbol("TSM", "TSMC posts record revenue on AI demand")


def test_mentioned_watch_symbols_retags_to_named_tickers():
    watch = ["AAPL", "MSFT", "NVDA", "TSM"]
    assert mentioned_watch_symbols(
        "TSMC Delivers Record Second-Quarter Revenue as AI Chip Demand Accelerates",
        watch,
    ) == ["TSM"]
    assert mentioned_watch_symbols("MSFT Stock Holds Up Amid Geopolitical Jitters", watch) == ["MSFT"]
    assert mentioned_watch_symbols("Chip stocks mixed pre-bell", watch) == []


def test_yfinance_drops_tsmc_headline_on_aapl_rail():
    aapl_rail = [
        {
            "id": "1",
            "content": {
                "title": "TSMC posts record revenue in second quarter on AI demand",
                "provider": {"displayName": "Reuters"},
            },
        },
        {
            "id": "2",
            "content": {
                "title": "Apple unveils new MacBook lineup",
                "provider": {"displayName": "Bloomberg"},
            },
        },
    ]

    class FakeTicker:
        def __init__(self, symbol: str):
            self.news = aapl_rail if symbol == "AAPL" else []

    with patch("yfinance.Ticker", FakeTicker):
        items = _fetch_yfinance_news(["AAPL", "MSFT", "TSM"])

    symbols = {i.symbol for i in items}
    headlines = {i.headline for i in items}
    assert "TSMC posts record revenue in second quarter on AI demand" not in {
        i.headline for i in items if i.symbol == "AAPL"
    }
    # TSMC story retagged to TSM when TSM is on the watch list
    assert any(i.symbol == "TSM" and "TSMC" in i.headline for i in items)
    assert any(i.symbol == "AAPL" and "Apple" in i.headline for i in items)
    assert "MSFT" not in symbols or all("MSFT" not in h for h in headlines)


def test_yfinance_drops_unrelated_if_named_symbol_not_on_watch():
    """Sector story with no watch-symbol mention is discarded entirely."""
    rail = [
        {
            "content": {
                "title": "TSMC posts record revenue in second quarter on AI demand",
            }
        }
    ]

    class FakeTicker:
        def __init__(self, symbol: str):
            self.news = rail if symbol == "AAPL" else []

    with patch("yfinance.Ticker", FakeTicker):
        items = _fetch_yfinance_news(["AAPL", "MSFT"])  # no TSM on watch

    assert items == []
