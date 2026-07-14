"""Breaking news and catalyst collector."""

from __future__ import annotations

import os
import re
from typing import Any, Iterable, List, Sequence

import requests

from trading_agent.config import AgentConfig
from trading_agent.discord.env import load_project_env
from trading_agent.models import NewsCatalysts, NewsItem

from .base import load_fixture, safe_fetch

FMP_STOCK_NEWS_URL = "https://financialmodelingprep.com/stable/news/stock-latest"

CATEGORY_KEYWORDS = {
    "earnings": ("earnings", "eps", "revenue", "guidance"),
    "analyst": ("upgrade", "downgrade", "price target", "initiates"),
    "sec_filing": ("sec", "10-k", "10-q", "8-k", "filing"),
    "insider": ("insider", "form 4", "director", "officer", "insider buying", "insider selling"),
    "ma": ("merger", "acquisition", "buyout", "takeover"),
    "contract": ("contract", "award", "government", "deal"),
    "ai": ("artificial intelligence", " generative ai", " openai", " llm"),
    "semiconductor": ("semiconductor", "chipmaker", "foundry", "wafer", "gpu demand"),
    "geopolitical": ("sanction", "geopolit", "conflict", "tariff", "war ", "ceasefire"),
}

# Company-name aliases so "Apple raises..." still attributes to AAPL.
# Keep aliases specific enough to avoid false positives (word-boundary matched).
SYMBOL_NAME_ALIASES: dict[str, tuple[str, ...]] = {
    "AAPL": ("apple",),
    "MSFT": ("microsoft",),
    "GOOGL": ("google", "alphabet"),
    "GOOG": ("google", "alphabet"),
    "AMZN": ("amazon",),
    "META": ("facebook", "meta platforms"),
    "NVDA": ("nvidia",),
    "TSLA": ("tesla",),
    "AMD": ("advanced micro devices",),
    "INTC": ("intel",),
    "TSM": ("tsmc", "taiwan semiconductor"),
    "AVGO": ("broadcom",),
    "QCOM": ("qualcomm",),
    "JPM": ("jpmorgan", "jp morgan", "j.p. morgan"),
    "XOM": ("exxon",),
    "CVX": ("chevron",),
}


def _classify(headline: str) -> str:
    lower = headline.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(k in lower for k in keywords):
            return category
    return "general"


def _token_in_text(token: str, text: str) -> bool:
    """Case-insensitive whole-token match (handles $AAPL, (AAPL), AAPL:)."""
    if not token or not text:
        return False
    pattern = rf"(?<![A-Za-z0-9])\$?{re.escape(token)}(?![A-Za-z0-9])"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def headline_mentions_symbol(symbol: str, headline: str) -> bool:
    """True only if the headline clearly refers to this symbol (ticker or alias)."""
    sym = (symbol or "").strip().upper()
    if not sym or not headline:
        return False
    if _token_in_text(sym, headline):
        return True
    for alias in SYMBOL_NAME_ALIASES.get(sym, ()):
        if _token_in_text(alias, headline):
            return True
    return False


def mentioned_watch_symbols(headline: str, watch: Sequence[str]) -> List[str]:
    """Return watch symbols clearly named in the headline (stable order)."""
    found: List[str] = []
    seen: set[str] = set()
    for raw in watch:
        sym = (raw or "").strip().upper()
        if not sym or sym in seen:
            continue
        if headline_mentions_symbol(sym, headline):
            seen.add(sym)
            found.append(sym)
    return found


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


def _append_items(
    items: List[NewsItem],
    seen: set[tuple[str, str]],
    symbols: Iterable[str],
    headline: str,
    source: str,
) -> None:
    category = _classify(headline)
    for symbol in symbols:
        dedupe_key = (symbol, headline.lower())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        items.append(
            NewsItem(
                symbol=symbol,
                headline=headline,
                source=source,
                category=category,
            )
        )


def _fetch_yfinance_news(symbols: List[str]) -> List[NewsItem]:
    """Pull per-ticker yfinance rails but only keep headlines that name the symbol.

    Yahoo often co-tags sector stories (e.g. TSMC revenue) onto mega-cap rails like
    AAPL. We never attribute a headline to the query symbol unless the title
    mentions that ticker/company; if it names other watch symbols, retag to those.
    """
    import yfinance as yf

    watch = [s.strip().upper() for s in symbols[:12] if s and str(s).strip()]
    items: List[NewsItem] = []
    seen: set[tuple[str, str]] = set()
    for symbol in watch:
        ticker = yf.Ticker(symbol)
        news = getattr(ticker, "news", None) or []
        for article in news[:4]:
            title = _article_field(article, "title")
            if not title:
                continue
            targets = mentioned_watch_symbols(title, watch)
            if not targets:
                continue
            publisher = _article_field(article, "publisher", "provider", "source") or "yfinance"
            _append_items(items, seen, targets, title, publisher)
    return items


def _fetch_fmp_stock_news(symbols: List[str], api_key: str) -> List[NewsItem]:
    watch_list = [s.strip().upper() for s in symbols[:12] if s and str(s).strip()]
    watch = set(watch_list)
    resp = requests.get(
        FMP_STOCK_NEWS_URL,
        params={"page": 0, "limit": 50, "apikey": api_key},
        timeout=15,
    )
    if resp.status_code == 402:
        raise PermissionError("FMP stock news requires a paid plan; using yfinance headlines")
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, list):
        return []

    items: List[NewsItem] = []
    seen: set[tuple[str, str]] = set()
    for row in payload:
        feed_symbol = (row.get("symbol") or row.get("ticker") or "").strip().upper()
        title = (row.get("title") or row.get("text") or "").strip()
        if not title:
            continue
        # Prefer symbols named in the headline; fall back to FMP symbol only if
        # the title actually refers to that name (avoids co-tagged junk).
        targets = mentioned_watch_symbols(title, watch_list)
        if not targets and feed_symbol and feed_symbol in watch and headline_mentions_symbol(
            feed_symbol, title
        ):
            targets = [feed_symbol]
        if not targets:
            continue
        source = row.get("site") or row.get("publisher") or "fmp"
        _append_items(items, seen, targets, title, str(source))
    return items


def _fixture_news() -> NewsCatalysts:
    data = load_fixture("news_catalysts.json")
    items = [NewsItem(**i) for i in data.get("items", [])]
    return NewsCatalysts(source="fixture", items=items)


def collect_news_catalysts(config: AgentConfig, symbols: List[str]) -> NewsCatalysts:
    """Live mode never injects fixture headlines into bias (empty if none found).

    Provider order (env-overridable via TRADING_AGENT_NEWS_PROVIDERS):
    yfinance → finnhub → tiingo → fmp → unavailable (no silent fixture fill).
    """
    if config.fixture_mode or not config.use_live_data:
        return _fixture_news()

    load_project_env()
    errors: List[str] = []
    items = safe_fetch(lambda: _fetch_yfinance_news(symbols), [], errors)

    if items:
        return NewsCatalysts(source="yfinance", items=items, errors=errors)

    # Secondary HTTP providers (Finnhub, Tiingo) via pluggable layer
    try:
        from trading_agent.providers.config import ProviderConfig
        from trading_agent.providers.news_providers import fetch_news_multi

        multi = fetch_news_multi(symbols, ProviderConfig.from_env())
        errors.extend(multi.errors)
        if multi.ok and multi.headlines:
            converted = [
                NewsItem(
                    symbol=h.symbol,
                    headline=h.headline,
                    source=h.source,
                    category=h.category,
                )
                for h in multi.headlines
            ]
            return NewsCatalysts(source=multi.source, items=converted, errors=errors)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"secondary news providers: {exc}")

    api_key = os.getenv("FMP_API_KEY", "").strip()
    if api_key:
        def _fetch_fmp() -> List[NewsItem]:
            try:
                return _fetch_fmp_stock_news(symbols, api_key)
            except PermissionError as exc:
                errors.append(str(exc))
                return []

        fmp_items = safe_fetch(_fetch_fmp, [], errors)
        if fmp_items:
            return NewsCatalysts(source="fmp", items=fmp_items, errors=errors)

    if not errors:
        errors.append("No live news headlines; catalysts omitted from bias (no fixture fill)")
    return NewsCatalysts(source="unavailable", items=[], errors=errors)