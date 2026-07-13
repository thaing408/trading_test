"""HTTP quote providers (env-gated). yfinance remains primary in market collector."""

from __future__ import annotations

from typing import Dict, List

from trading_agent.providers.base import ProviderFetchResult, QuoteResult, http_get
from trading_agent.providers.config import ProviderConfig


def fetch_finnhub_quote(symbol: str, api_key: str) -> QuoteResult | None:
    resp = http_get(
        "https://finnhub.io/api/v1/quote",
        params={"symbol": symbol, "token": api_key},
    )
    resp.raise_for_status()
    data = resp.json()
    last = float(data.get("c") or 0)
    prev = float(data.get("pc") or 0)
    if last <= 0:
        return None
    chg = ((last - prev) / prev * 100) if prev else 0.0
    return QuoteResult(
        symbol=symbol,
        last=last,
        change_pct=round(chg, 2),
        source="finnhub",
        raw=data if isinstance(data, dict) else {},
    )


def fetch_alpha_vantage_quote(symbol: str, api_key: str) -> QuoteResult | None:
    resp = http_get(
        "https://www.alphavantage.co/query",
        params={
            "function": "GLOBAL_QUOTE",
            "symbol": symbol,
            "apikey": api_key,
        },
    )
    resp.raise_for_status()
    data = resp.json()
    gq = data.get("Global Quote") or data.get("globalQuote") or {}
    if not gq:
        return None
    last = float(gq.get("05. price") or gq.get("price") or 0)
    chg = float(gq.get("10. change percent", "0").replace("%", "") or 0)
    if last <= 0:
        return None
    return QuoteResult(
        symbol=symbol,
        last=last,
        change_pct=round(chg, 2),
        source="alpha_vantage",
        raw=gq,
    )


def fetch_twelve_data_quote(symbol: str, api_key: str) -> QuoteResult | None:
    resp = http_get(
        "https://api.twelvedata.com/quote",
        params={"symbol": symbol, "apikey": api_key},
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") == "error":
        return None
    last = float(data.get("close") or data.get("price") or 0)
    chg = float(data.get("percent_change") or 0)
    if last <= 0:
        return None
    return QuoteResult(
        symbol=symbol,
        last=last,
        change_pct=round(chg, 2),
        source="twelve_data",
        raw=data if isinstance(data, dict) else {},
    )


def fetch_tiingo_quote(symbol: str, api_key: str) -> QuoteResult | None:
    resp = http_get(
        f"https://api.tiingo.com/iex/{symbol}",
        headers={"Content-Type": "application/json", "Authorization": f"Token {api_key}"},
    )
    resp.raise_for_status()
    data = resp.json()
    row = data[0] if isinstance(data, list) and data else data
    if not isinstance(row, dict):
        return None
    last = float(row.get("tngoLast") or row.get("last") or row.get("close") or 0)
    prev = float(row.get("prevClose") or 0)
    if last <= 0:
        return None
    chg = ((last - prev) / prev * 100) if prev else 0.0
    return QuoteResult(
        symbol=symbol,
        last=last,
        change_pct=round(chg, 2),
        source="tiingo",
        raw=row,
    )


def fetch_marketstack_quote(symbol: str, api_key: str) -> QuoteResult | None:
    resp = http_get(
        "http://api.marketstack.com/v1/eod/latest",
        params={"access_key": api_key, "symbols": symbol},
    )
    resp.raise_for_status()
    data = resp.json()
    rows = data.get("data") or []
    if not rows:
        return None
    row = rows[0]
    last = float(row.get("close") or 0)
    # marketstack latest eod may not include prior close in same payload
    chg = 0.0
    if last <= 0:
        return None
    return QuoteResult(
        symbol=symbol,
        last=last,
        change_pct=chg,
        source="marketstack",
        raw=row,
    )


_QUOTE_FETCHERS = {
    "finnhub": fetch_finnhub_quote,
    "alpha_vantage": fetch_alpha_vantage_quote,
    "twelve_data": fetch_twelve_data_quote,
    "tiingo": fetch_tiingo_quote,
    "marketstack": fetch_marketstack_quote,
}


def fetch_quotes_multi(
    symbols: List[str],
    config: ProviderConfig | None = None,
    preferred: List[str] | None = None,
) -> ProviderFetchResult:
    """Try configured quote providers in order (skipping yfinance — handled by collectors).

    Returns first provider that yields at least one quote, or unavailable.
    """
    cfg = config or ProviderConfig.from_env()
    order = preferred or [p for p in cfg.quote_providers if p != "yfinance"]
    errors: list[str] = []

    for provider in order:
        if not cfg.is_configured(provider):
            errors.append(f"{provider}: not configured (missing API key)")
            continue
        fetcher = _QUOTE_FETCHERS.get(provider)
        if not fetcher:
            errors.append(f"{provider}: no HTTP quote adapter in this build")
            continue
        key = cfg.key_for(provider)
        quotes: Dict[str, QuoteResult] = {}
        for sym in symbols:
            try:
                q = fetcher(sym, key)
                if q:
                    quotes[sym] = q
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{provider}/{sym}: {exc}")
        if quotes:
            return ProviderFetchResult(
                source=provider,
                ok=True,
                quotes=quotes,
                errors=errors,
                metadata={"status": "ok", "symbols": str(len(quotes))},
            )

    return ProviderFetchResult.unavailable(
        "unavailable",
        "; ".join(errors) if errors else "No secondary quote provider configured",
    )
