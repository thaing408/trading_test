"""Tests for yfinance nested news article parsing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from trading_agent.collectors.news import _article_field, _fetch_yfinance_news


def test_article_field_reads_nested_content_title():
    article = {
        "id": "abc",
        "content": {
            "title": "Chip stocks regain ground after volatile week",
            "pubDate": "2026-07-10T14:30:00Z",
        },
    }
    assert _article_field(article, "title") == "Chip stocks regain ground after volatile week"


def test_fetch_yfinance_news_parses_nested_articles():
    nested = [
        {
            "id": "1",
            "content": {
                "title": "NVDA supplier raises full-year outlook",
                "provider": {"displayName": "Reuters"},
            },
        }
    ]

    class FakeTicker:
        def __init__(self, symbol: str):
            self.news = nested if symbol == "NVDA" else []

    with patch("yfinance.Ticker", FakeTicker):
        items = _fetch_yfinance_news(["NVDA", "AAPL"])

    assert len(items) == 1
    assert items[0].symbol == "NVDA"
    assert "outlook" in items[0].headline.lower()
    assert items[0].category in ("earnings", "general", "analyst")