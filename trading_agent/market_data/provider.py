"""Unified OHLCV: IBKR research (optional) → Schwab → yfinance.

IBKR is research-only (historical bars). Never places orders from this module.
Enable with IBKR_ENABLED=1 and a running TWS/Gateway API socket.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional

from trading_agent.config import AgentConfig

logger = logging.getLogger(__name__)

_LAST_SOURCE: dict[str, str] = {}
_YF_CACHE: dict[tuple[str, str, str], Dict[str, List[float]]] = {}


def last_ohlcv_source(symbol: Optional[str] = None) -> str:
    """Return last provider used (per symbol or overall summary)."""
    if symbol:
        return _LAST_SOURCE.get(symbol.upper(), "unknown")
    if not _LAST_SOURCE:
        return "unknown"
    # majority vote for debugging
    from collections import Counter

    return Counter(_LAST_SOURCE.values()).most_common(1)[0][0]


def reset_ohlcv_cache() -> None:
    from trading_agent.market_data.schwab_ohlcv import clear_schwab_cache

    clear_schwab_cache()
    try:
        from trading_agent.market_data.ibkr_ohlcv import clear_ibkr_cache

        clear_ibkr_cache()
    except Exception:  # noqa: BLE001
        pass
    _YF_CACHE.clear()
    _LAST_SOURCE.clear()


def _provider_pref(config: AgentConfig | None) -> str:
    if config is not None and getattr(config, "market_data_provider", None):
        return str(config.market_data_provider).strip().lower()
    return os.getenv("TRADING_AGENT_MARKET_DATA", "auto").strip().lower() or "auto"


def _ibkr_enabled() -> bool:
    return os.getenv("IBKR_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def _yfinance_ohlcv(symbol: str, interval: str, period: str) -> Dict[str, List[float]]:
    key = (symbol.upper(), interval, period)
    if key in _YF_CACHE:
        return {k: list(v) for k, v in _YF_CACHE[key].items()}

    import yfinance as yf

    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=period, interval=interval)
    if hist.empty:
        return {"close": [], "high": [], "low": [], "volume": []}
    result: Dict[str, List[float]] = {
        "close": hist["Close"].tolist(),
        "high": hist["High"].tolist(),
        "low": hist["Low"].tolist(),
        "volume": hist["Volume"].tolist(),
    }
    if "Open" in hist.columns:
        result["open"] = hist["Open"].tolist()
    _YF_CACHE[key] = result
    return {k: list(v) for k, v in result.items()}


def get_ohlcv(
    symbol: str,
    config: AgentConfig | None = None,
    interval: str = "1d",
    period: str = "3mo",
) -> Dict[str, List[float]]:
    """
    Load OHLCV bars for strength gates and technical analysis.

    Provider preference (TRADING_AGENT_MARKET_DATA or config.market_data_provider):
      - auto (default): IBKR (if IBKR_ENABLED) → Schwab → yfinance
      - ibkr: IBKR research only (empty on failure)
      - schwab: Schwab only (empty on failure)
      - yfinance: yfinance only
    """
    if config is not None and config.fixture_mode:
        from trading_agent.collectors.base import load_fixture

        data = load_fixture("ohlcv.json").get(symbol, {})
        if interval in ("1h", "60m", "30m", "15m"):
            # Prefer matching TF keys when present; fall back to hourly / daily
            key = {"1h": "hourly", "60m": "hourly", "30m": "m30", "15m": "m15"}.get(
                interval, "hourly"
            )
            block = data.get(key) or data.get("hourly") or {}
            if block:
                out = {
                    "close": block.get("close", []),
                    "high": block.get("high", []),
                    "low": block.get("low", []),
                    "volume": block.get("volume", []),
                }
                if block.get("open"):
                    out["open"] = block["open"]
                _LAST_SOURCE[symbol.upper()] = "fixture"
                return out
        out = {
            "close": data.get("close", []),
            "high": data.get("high", []),
            "low": data.get("low", []),
            "volume": data.get("volume", []),
        }
        if data.get("open"):
            out["open"] = data["open"]
        _LAST_SOURCE[symbol.upper()] = "fixture"
        return out

    pref = _provider_pref(config)
    empty = {"close": [], "high": [], "low": [], "volume": []}

    want_ibkr = pref in ("auto", "ibkr", "ibkr_tws", "tws") and (
        pref != "auto" or _ibkr_enabled()
    )
    want_schwab = pref in ("auto", "schwab")
    want_yf = pref in ("auto", "yfinance", "yf")

    # Research-only IBKR (never used for order placement in this module)
    if want_ibkr:
        try:
            from trading_agent.market_data.ibkr_ohlcv import (
                fetch_ibkr_ohlcv,
                ibkr_available,
                last_ibkr_error,
            )

            if ibkr_available():
                bars = fetch_ibkr_ohlcv(symbol, interval=interval, period=period)
                if bars.get("close"):
                    _LAST_SOURCE[symbol.upper()] = "ibkr"
                    return bars
                logger.warning(
                    "IBKR empty bars for %s %s/%s (%s)",
                    symbol,
                    interval,
                    period,
                    last_ibkr_error() or "no data",
                )
            elif pref in ("ibkr", "ibkr_tws", "tws"):
                logger.warning("IBKR not available for %s", symbol)
                _LAST_SOURCE[symbol.upper()] = "ibkr_unavailable"
                return empty
        except Exception as exc:  # noqa: BLE001
            logger.warning("IBKR OHLCV failed for %s: %s", symbol, exc)
            if pref in ("ibkr", "ibkr_tws", "tws"):
                _LAST_SOURCE[symbol.upper()] = "ibkr_error"
                return empty

    if want_schwab:
        try:
            from trading_agent.market_data.schwab_ohlcv import (
                fetch_schwab_ohlcv,
                schwab_available,
            )

            if schwab_available():
                bars = fetch_schwab_ohlcv(symbol, interval=interval, period=period)
                if bars.get("close"):
                    _LAST_SOURCE[symbol.upper()] = "schwab"
                    return bars
                logger.warning("Schwab empty bars for %s %s/%s", symbol, interval, period)
            elif pref == "schwab":
                logger.warning("Schwab token not available for %s", symbol)
        except Exception as exc:  # noqa: BLE001 — fall back for research continuity
            logger.warning("Schwab OHLCV failed for %s (%s/%s): %s", symbol, interval, period, exc)
            if pref == "schwab":
                _LAST_SOURCE[symbol.upper()] = "schwab_error"
                return empty

    if want_yf:
        try:
            bars = _yfinance_ohlcv(symbol, interval, period)
            _LAST_SOURCE[symbol.upper()] = "yfinance"
            return bars
        except Exception as exc:  # noqa: BLE001
            logger.warning("yfinance OHLCV failed for %s: %s", symbol, exc)
            _LAST_SOURCE[symbol.upper()] = "yfinance_error"
            return empty

    _LAST_SOURCE[symbol.upper()] = "unavailable"
    return empty
