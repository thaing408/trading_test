"""Overnight global market data collector."""

from __future__ import annotations

from typing import Any, Dict, List

from trading_agent.config import AgentConfig
from trading_agent.models import MarketSnapshot

from .base import load_fixture, safe_fetch

# Named ETF set required by Market Intelligence institutional brief.
ETF_TICKERS = {
    "SPY": "SPY",
    "QQQ": "QQQ",
    "IWM": "IWM",
    "DIA": "DIA",
    "XLK": "XLK",
    "SMH": "SMH",
    "SOXX": "SOXX",
    "XLF": "XLF",
    "XLE": "XLE",
    "XBI": "XBI",
}

MARKET_TICKERS = {
    "futures": {"ES": "ES=F", "NQ": "NQ=F", "YM": "YM=F", "RTY": "RTY=F"},
    # Asia + Europe for global equities overnight context
    "international": {
        "NIKKEI": "^N225",
        "HSI": "^HSI",
        "SHANGHAI": "000001.SS",
        "ASX": "^AXJO",
        "KOSPI": "^KS11",
        "FTSE": "^FTSE",
        "DAX": "^GDAXI",
        "CAC": "^FCHI",
        "STOXX50": "^STOXX50E",
    },
    "bonds": {"TLT": "TLT", "IEF": "IEF", "SHY": "SHY"},
    "dollar_index": {"DXY": "DX-Y.NYB"},
    # Spot VIX + 3M for term structure proxy
    "vix": {"VIX": "^VIX", "VIX3M": "^VIX3M"},
    "commodities": {
        "OIL": "CL=F",
        "NATGAS": "NG=F",
        "GOLD": "GC=F",
        "SILVER": "SI=F",
        "COPPER": "HG=F",
    },
    "crypto": {"BTC": "BTC-USD", "ETH": "ETH-USD"},
    "sector_rotation": {
        "XLK": "XLK",
        "XLF": "XLF",
        "XLE": "XLE",
        "XLV": "XLV",
        "XLI": "XLI",
        "XLY": "XLY",
        "XLP": "XLP",
        "XLU": "XLU",
        "XLB": "XLB",
        "XLRE": "XLRE",
        "XLC": "XLC",
    },
    "etfs": ETF_TICKERS,
    "treasury_yields": {
        "US2Y": "^IRX",
        "US10Y": "^TNX",
        "US30Y": "^TYX",
    },
}

# Series with no reliable free yfinance feed — always marked unavailable on live path.
HARD_UNAVAILABLE_LIVE = {
    "MOVE": "MOVE Index not available via free market data feed",
    "CME_FEDWATCH": "CME FedWatch probabilities require dedicated CME/DTCC feed",
    "ADVANCE_DECLINE": "NYSE Advance/Decline line not available via free feed",
    "NEW_HIGHS_LOWS": "New highs vs new lows not available via free feed",
    "PCT_ABOVE_20EMA": "Universe % above 20 EMA not available without full tape",
    "PCT_ABOVE_50EMA": "Universe % above 50 EMA not available without full tape",
    "PCT_ABOVE_200EMA": "Universe % above 200 EMA not available without full tape",
    "PUT_CALL_RATIO": "Equity put/call ratio not available via free feed",
    "TRIN": "TRIN (Arms Index) not available via free feed",
    "TICK": "NYSE TICK not available via free feed",
}


def _is_finite_number(value: Any) -> bool:
    """True for finite ints/floats; rejects NaN/inf and non-numeric."""
    try:
        import math

        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _quote_summary(symbol: str) -> Dict[str, Any]:
    import math

    import yfinance as yf

    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="5d", interval="1d")
    if hist.empty:
        raise ValueError(f"No history for {symbol}")
    last = float(hist["Close"].iloc[-1])
    prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else last
    if not math.isfinite(last) or not math.isfinite(prev):
        raise ValueError(f"Non-finite price for {symbol}: last={last} prev={prev}")
    if prev == 0.0:
        change_pct = 0.0
    else:
        change_pct = (last - prev) / prev * 100
    if not math.isfinite(change_pct):
        raise ValueError(f"Non-finite change_pct for {symbol}: {change_pct}")
    return {"symbol": symbol, "last": last, "change_pct": round(change_pct, 2)}


def _fetch_group(group: Dict[str, str], errors: List[str]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for name, symbol in group.items():
        data = safe_fetch(lambda s=symbol: _quote_summary(s), {}, errors)
        # Drop empty dicts and any accidental non-finite payloads
        if not data:
            continue
        last = data.get("last")
        chg = data.get("change_pct")
        if not _is_finite_number(last) or not _is_finite_number(chg):
            errors.append(f"Dropped {name} ({symbol}): non-finite quote fields")
            continue
        result[name] = data
    return result


def _breadth_from_payload(data: dict) -> Dict[str, Any]:
    """Normalize breadth map; every key must expose status ok|unavailable."""
    raw = data.get("breadth") or {}
    if not raw:
        return {
            key: {"status": "unavailable", "note": note}
            for key, note in HARD_UNAVAILABLE_LIVE.items()
            if key
            in (
                "ADVANCE_DECLINE",
                "NEW_HIGHS_LOWS",
                "PCT_ABOVE_20EMA",
                "PCT_ABOVE_50EMA",
                "PCT_ABOVE_200EMA",
                "PUT_CALL_RATIO",
                "TRIN",
                "TICK",
            )
        }
    out: Dict[str, Any] = {}
    for key, val in raw.items():
        if isinstance(val, dict) and val.get("status"):
            out[key] = val
        else:
            out[key] = {"status": "ok", "value": val}
    return out


def _from_fixture() -> MarketSnapshot:
    data = load_fixture("market_snapshot.json")
    unavailable = dict(data.get("unavailable") or {})
    breadth = _breadth_from_payload(data)
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
        etfs=data.get("etfs", {}),
        treasury_yields=data.get("treasury_yields", {}),
        breadth=breadth,
        unavailable=unavailable,
    )


def collect_market_snapshot(config: AgentConfig) -> MarketSnapshot:
    if config.fixture_mode or not config.use_live_data:
        return _from_fixture()

    errors: List[str] = []
    futures = _fetch_group(MARKET_TICKERS["futures"], errors)
    international = _fetch_group(MARKET_TICKERS["international"], errors)
    bonds = _fetch_group(MARKET_TICKERS["bonds"], errors)
    dollar_index = _fetch_group(MARKET_TICKERS["dollar_index"], errors)
    vix = _fetch_group(MARKET_TICKERS["vix"], errors)
    commodities = _fetch_group(MARKET_TICKERS["commodities"], errors)
    crypto = _fetch_group(MARKET_TICKERS["crypto"], errors)
    sector_rotation = _fetch_group(MARKET_TICKERS["sector_rotation"], errors)
    etfs = _fetch_group(MARKET_TICKERS["etfs"], errors)
    treasury_yields = _fetch_group(MARKET_TICKERS["treasury_yields"], errors)

    breadth: Dict[str, Any] = {
        key: {"status": "unavailable", "note": note}
        for key, note in HARD_UNAVAILABLE_LIVE.items()
        if key
        in (
            "ADVANCE_DECLINE",
            "NEW_HIGHS_LOWS",
            "PCT_ABOVE_20EMA",
            "PCT_ABOVE_50EMA",
            "PCT_ABOVE_200EMA",
            "PUT_CALL_RATIO",
            "TRIN",
            "TICK",
        )
    }
    unavailable = {
        k: v
        for k, v in HARD_UNAVAILABLE_LIVE.items()
        if k in ("MOVE", "CME_FEDWATCH")
    }
    if "VIX3M" not in vix:
        unavailable["VIX_TERM"] = "VIX3M term structure proxy not fetched"

    return MarketSnapshot(
        source="yfinance",
        futures=futures,
        international=international,
        bonds=bonds,
        dollar_index=dollar_index,
        vix=vix,
        commodities=commodities,
        crypto=crypto,
        sector_rotation=sector_rotation,
        etfs=etfs,
        treasury_yields=treasury_yields,
        breadth=breadth,
        unavailable=unavailable,
        errors=errors,
    )
