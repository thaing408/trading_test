"""Breaking news and catalyst collector."""

from __future__ import annotations

from typing import List

from trading_agent.config import AgentConfig
from trading_agent.models import NewsCatalysts, NewsItem

from .base import load_fixture, safe_fetch

CATEGORY_KEYWORDS = {
    "earnings": ("earnings", "eps", "revenue", "guidance"),
    "analyst": ("upgrade", "downgrade", "price target", "initiates"),
    "sec_filing": ("sec", "10-k", "10-q", "8-k", "filing"),
    "insider": ("insider", "form 4", "director", "officer"),
    "ma": ("merger", "acquisition", "buyout", "takeover"),
    "contract": ("contract", "award", "government", "deal"),
}


def _classify(headline: str) -> str:
    lower = headline.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(k in lower for k in keywords):
            return category
    return "general"


def _fetch_yfinance_news(symbols: List[str]) -> List[NewsItem]:
    import yfinance as yf

    items: List[NewsItem] = []
    for symbol in symbols[:8]:
        ticker = yf.Ticker(symbol)
        news = getattr(ticker, "news", None) or []
        for article in news[:3]:
            title = article.get("title", "")
            if not title:
                continue
            items.append(
                NewsItem(
                    symbol=symbol,
                    headline=title,
                    source=article.get("publisher", "yfinance"),
                    category=_classify(title),
                )
            )
    return items


def _fixture_news() -> NewsCatalysts:
    data = load_fixture("news_catalysts.json")
    items = [NewsItem(**i) for i in data.get("items", [])]
    return NewsCatalysts(source="fixture", items=items)


def collect_news_catalysts(config: AgentConfig, symbols: List[str]) -> NewsCatalysts:
    if config.fixture_mode or not config.use_live_data:
        return _fixture_news()

    errors: List[str] = []
    items = safe_fetch(lambda: _fetch_yfinance_news(symbols), [], errors)
    if not items:
        news = _fixture_news()
        news.errors.extend(errors)
        news.source = "fixture-fallback"
        return news
    return NewsCatalysts(source="yfinance", items=items, errors=errors)