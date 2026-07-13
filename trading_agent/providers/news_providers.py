"""HTTP news providers (env-gated)."""

from __future__ import annotations

from typing import List

from trading_agent.providers.base import NewsHeadline, ProviderFetchResult, http_get
from trading_agent.providers.config import ProviderConfig


def _classify(headline: str) -> str:
    lower = headline.lower()
    rules = {
        "earnings": ("earnings", "eps", "revenue", "guidance"),
        "analyst": ("upgrade", "downgrade", "price target"),
        "insider": ("insider", "form 4"),
        "contract": ("contract", "award", "government"),
    }
    for cat, keys in rules.items():
        if any(k in lower for k in keys):
            return cat
    return "general"


def fetch_finnhub_news(symbols: List[str], api_key: str, limit: int = 20) -> List[NewsHeadline]:
    items: List[NewsHeadline] = []
    for symbol in symbols[:8]:
        resp = http_get(
            "https://finnhub.io/api/v1/company-news",
            params={
                "symbol": symbol,
                "from": "2020-01-01",
                "to": "2099-12-31",
                "token": api_key,
            },
        )
        if resp.status_code == 403:
            raise PermissionError("Finnhub news forbidden — check API key/plan")
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, list):
            continue
        for row in payload[:4]:
            title = (row.get("headline") or row.get("summary") or "").strip()
            if not title:
                continue
            items.append(
                NewsHeadline(
                    symbol=symbol,
                    headline=title,
                    source=row.get("source") or "finnhub",
                    provider="finnhub",
                    category=_classify(title),
                )
            )
            if len(items) >= limit:
                return items
    return items


def fetch_tiingo_news(symbols: List[str], api_key: str, limit: int = 20) -> List[NewsHeadline]:
    tickers = ",".join(symbols[:8])
    resp = http_get(
        "https://api.tiingo.com/tiingo/news",
        params={"tickers": tickers, "limit": limit},
        headers={"Content-Type": "application/json", "Authorization": f"Token {api_key}"},
    )
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, list):
        return []
    items: List[NewsHeadline] = []
    for row in payload[:limit]:
        title = (row.get("title") or row.get("description") or "").strip()
        if not title:
            continue
        tickers_list = row.get("tickers") or symbols[:1]
        symbol = str(tickers_list[0]).upper() if tickers_list else "MKT"
        items.append(
            NewsHeadline(
                symbol=symbol,
                headline=title,
                source=row.get("source") or "tiingo",
                provider="tiingo",
                category=_classify(title),
            )
        )
    return items


def fetch_news_multi(
    symbols: List[str],
    config: ProviderConfig | None = None,
    preferred: List[str] | None = None,
) -> ProviderFetchResult:
    """Try secondary news providers (not yfinance/fmp — those stay in collectors)."""
    cfg = config or ProviderConfig.from_env()
    order = preferred or [
        p for p in cfg.news_providers if p not in ("yfinance", "fmp")
    ]
    errors: list[str] = []

    for provider in order:
        if not cfg.is_configured(provider):
            errors.append(f"{provider}: not configured (missing API key)")
            continue
        try:
            if provider == "finnhub":
                headlines = fetch_finnhub_news(symbols, cfg.finnhub_api_key)
            elif provider == "tiingo":
                headlines = fetch_tiingo_news(symbols, cfg.tiingo_api_key)
            else:
                errors.append(f"{provider}: no news adapter in this build")
                continue
            if headlines:
                return ProviderFetchResult(
                    source=provider,
                    ok=True,
                    headlines=headlines,
                    errors=errors,
                    metadata={"status": "ok", "count": str(len(headlines))},
                )
            errors.append(f"{provider}: empty news payload")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{provider}: {exc}")

    return ProviderFetchResult.unavailable(
        "unavailable",
        "; ".join(errors) if errors else "No secondary news provider configured",
    )
