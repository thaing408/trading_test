"""Overnight global market data collector."""

from __future__ import annotations

from typing import Any, Dict, List

from trading_agent.config import AgentConfig
from trading_agent.models import MarketSnapshot

from .base import load_fixture, safe_fetch

MARKET_TICKERS = {
    "futures": {"ES": "ES=F", "NQ": "NQ=F", "YM": "YM=F", "RTY": "RTY=F"},
    "international": {"FTSE": "^FTSE", "DAX": "^GDAXI", "NIKKEI": "^N225", "HSI": "^HSI"},
    "bonds": {"TLT": "TLT", "IEF": "IEF", "SHY": "SHY"},
    "dollar_index": {"DXY": "DX-Y.NYB"},
    "vix": {"VIX": "^VIX"},
    "commodities": {"GOLD": "GC=F", "OIL": "CL=F", "SILVER": "SI=F"},
    "crypto": {"BTC": "BTC-USD", "ETH": "ETH-USD"},
    "sector_rotation": {
        "XLK": "XLK", "XLF": "XLF", "XLE": "XLE", "XLV": "XLV",
        "XLI": "XLI", "XLY": "XLY", "XLP": "XLP", "XLU": "XLU",
    },
}


def _quote_summary(symbol: str) -> Dict[str, Any]:
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="5d", interval="1d")
    if hist.empty:
        raise ValueError(f"No history for {symbol}")
    last = float(hist["Close"].iloc[-1])
    prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else last
    change_pct = ((last - prev) / prev * 100) if prev else 0.0
    return {"symbol": symbol, "last": last, "change_pct": round(change_pct, 2)}


def _fetch_group(group: Dict[str, str], errors: List[str]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for name, symbol in group.items():
        data = safe_fetch(lambda s=symbol: _quote_summary(s), {}, errors)
        if data:
            result[name] = data
    return result


def _from_fixture() -> MarketSnapshot:
    data = load_fixture("market_snapshot.json")
    return MarketSnapshot(
        source="fixture",
        futures=data.get("futures", {}),
        international=data.get("international", {}),
        bonds=data.get("bonds", {}),
        dollar_index=data.get("dollar_index", {}),
        vix=data.get("vix", {}),
        commodities=data.get("commodities", {}),
        crypto=data.get("crypto", {}),
        sector_rotation=data.get("sector_rotation", {}),
    )


def collect_market_snapshot(config: AgentConfig) -> MarketSnapshot:
    if config.fixture_mode or not config.use_live_data:
        return _from_fixture()

    errors: List[str] = []
    return MarketSnapshot(
        source="yfinance",
        futures=_fetch_group(MARKET_TICKERS["futures"], errors),
        international=_fetch_group(MARKET_TICKERS["international"], errors),
        bonds=_fetch_group(MARKET_TICKERS["bonds"], errors),
        dollar_index=_fetch_group(MARKET_TICKERS["dollar_index"], errors),
        vix=_fetch_group(MARKET_TICKERS["vix"], errors),
        commodities=_fetch_group(MARKET_TICKERS["commodities"], errors),
        crypto=_fetch_group(MARKET_TICKERS["crypto"], errors),
        sector_rotation=_fetch_group(MARKET_TICKERS["sector_rotation"], errors),
        errors=errors,
    )