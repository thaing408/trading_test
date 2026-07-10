"""Breaking news and catalyst collector."""

from __future__ import annotations

import os
from typing import Any, List

import requests

from trading_agent.config import AgentConfig
from trading_agent.discord.env import load_project_env
from trading_agent.models import NewsCatalysts, NewsItem

from .base import load_fixture, safe_fetch

FMP_STOCK_NEWS_URL = "https://financialmodelingprep.com/api/v3/stock_news"

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


def _article_field(article: dict[str, Any], *keys: str) -> str:
    """Read a field from yfinance's flat or nested {content:{...}} article shape."""
    for key in keys:
        value = article.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    content = article.get("content")
    if isinstance(content, dict):
        for key in keys:
            value = content.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _fetch_yfinance_news(symbols: List[str]) -> List[NewsItem]:
    import yfinance as yf

    items: List[NewsItem] = []
    seen: set[tuple[str, str]] = set()
    for symbol in symbols[:12]:
        ticker = yf.Ticker(symbol)
        news = getattr(ticker, "news", None) or []
        for article in news[:4]:
            title = _article_field(article, "title")
            if not title:
                continue
            dedupe_key = (symbol, title.lower())
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            publisher = _article_field(article, "publisher", "provider", "source") or "yfinance"
            items.append(
                NewsItem(
                    symbol=symbol,
                    headline=title,
                    source=publisher,
                    category=_classify(title),
                )
            )
    return items


def _fetch_fmp_stock_news(symbols: List[str], api_key: str) -> List[NewsItem]:
    tickers = ",".join(symbols[:10])
    resp = requests.get(
        FMP_STOCK_NEWS_URL,
        params={"tickers": tickers, "limit": 25, "apikey": api_key},
        timeout=15,
    )
    resp.raise_for_status()
    items: List[NewsItem] = []
    seen: set[tuple[str, str]] = set()
    for row in resp.json():
        symbol = (row.get("symbol") or "").strip().upper()
        title = (row.get("title") or "").strip()
        if not symbol or not title:
            continue
        dedupe_key = (symbol, title.lower())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        items.append(
            NewsItem(
                symbol=symbol,
                headline=title,
                source=row.get("site", "fmp"),
                category=_classify(title),
            )
        )
    return items


def _fixture_news() -> NewsCatalysts:
    data = load_fixture("news_catalysts.json")
    items = [NewsItem(**i) for i in data.get("items", [])]
    return NewsCatalysts(source="fixture", items=items)


def collect_news_catalysts(config: AgentConfig, symbols: List[str]) -> NewsCatalysts:
    """Live mode never injects fixture headlines into bias (empty if none found)."""
    if config.fixture_mode or not config.use_live_data:
        return _fixture_news()

    load_project_env()
    errors: List[str] = []
    items = safe_fetch(lambda: _fetch_yfinance_news(symbols), [], errors)

    if not items:
        api_key = os.getenv("FMP_API_KEY", "").strip()
        if api_key:
            fmp_items = safe_fetch(lambda: _fetch_fmp_stock_news(symbols, api_key), [], errors)
            if fmp_items:
                return NewsCatalysts(source="fmp", items=fmp_items, errors=errors)

    if not items:
        if not errors:
            errors.append("No live news headlines; catalysts omitted from bias (no fixture fill)")
        return NewsCatalysts(source="unavailable", items=[], errors=errors)

    return NewsCatalysts(source="yfinance", items=items, errors=errors)