"""Read-only IBKR (TWS/Gateway) historical OHLCV for research.

Research-only: never places orders. Requires a running TWS/IB Gateway with
API socket enabled. Prefer Read-Only API in TWS settings.

Env:
  IBKR_ENABLED=1
  IBKR_HOST=127.0.0.1
  IBKR_PORT=7496          # TWS live 7496, paper 7497; Gateway live 4001, paper 4002
  IBKR_CLIENT_ID=17
  IBKR_READONLY=1         # default on
  IBKR_CONNECT_TIMEOUT=15
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_IB = None  # ib_insync.IB | None
_CACHE: dict[tuple[str, str, str], Dict[str, List[float]]] = {}
_LAST_ERROR: str = ""

# Space requests slightly to reduce IB pacing violations
_MIN_HIST_GAP_SEC = 0.35
_last_hist_ts = 0.0


def ibkr_config() -> Dict[str, Any]:
    return {
        "enabled": os.getenv("IBKR_ENABLED", "").strip().lower() in ("1", "true", "yes", "on"),
        "host": os.getenv("IBKR_HOST", "127.0.0.1").strip() or "127.0.0.1",
        "port": int(os.getenv("IBKR_PORT", "7496") or 7496),
        "client_id": int(os.getenv("IBKR_CLIENT_ID", "17") or 17),
        "readonly": os.getenv("IBKR_READONLY", "1").strip().lower()
        not in ("0", "false", "no", "off"),
        "timeout": float(os.getenv("IBKR_CONNECT_TIMEOUT", "15") or 15),
    }


def ibkr_enabled() -> bool:
    return bool(ibkr_config()["enabled"])


def ibkr_available() -> bool:
    """True if enabled and ib_insync importable (does not guarantee TWS is up)."""
    if not ibkr_enabled():
        return False
    try:
        import ib_insync  # noqa: F401

        return True
    except ImportError:
        return False


def last_ibkr_error() -> str:
    return _LAST_ERROR


def clear_ibkr_cache() -> None:
    _CACHE.clear()


def disconnect_ibkr() -> None:
    """Drop shared connection (tests / shutdown)."""
    global _IB
    with _LOCK:
        if _IB is not None:
            try:
                if getattr(_IB, "isConnected", lambda: False)():
                    _IB.disconnect()
            except Exception:  # noqa: BLE001
                pass
            _IB = None


def _map_period_duration(period: str) -> str:
    """Map yfinance-style period to IB durationStr."""
    p = (period or "1y").strip().lower()
    table = {
        "1d": "1 D",
        "5d": "5 D",
        "1wk": "1 W",
        "1mo": "1 M",
        "3mo": "3 M",
        "6mo": "6 M",
        "1y": "1 Y",
        "2y": "2 Y",
        "5y": "5 Y",
        "10y": "10 Y",
        "ytd": "1 Y",
        "max": "10 Y",
        "60d": "60 D",
        "30d": "30 D",
        "7d": "7 D",
        "14d": "14 D",
    }
    if p in table:
        return table[p]
    # bare numbers like 60d already covered; try Nd / Nm / Ny
    if p.endswith("d") and p[:-1].isdigit():
        return f"{int(p[:-1])} D"
    if p.endswith("mo") and p[:-2].isdigit():
        return f"{int(p[:-2])} M"
    if p.endswith("y") and p[:-1].isdigit():
        return f"{int(p[:-1])} Y"
    return "1 Y"


def _map_bar_size(interval: str) -> str:
    """Map yfinance-style interval to IB barSizeSetting."""
    i = (interval or "1d").strip().lower()
    table = {
        "1m": "1 min",
        "1min": "1 min",
        "2m": "2 mins",
        "5m": "5 mins",
        "15m": "15 mins",
        "30m": "30 mins",
        "60m": "1 hour",
        "1h": "1 hour",
        "90m": "1 hour",
        "1d": "1 day",
        "d": "1 day",
        "day": "1 day",
        "daily": "1 day",
        "1wk": "1 week",
        "1w": "1 week",
        "1mo": "1 month",
    }
    return table.get(i, "1 day")


def _pace() -> None:
    global _last_hist_ts
    now = time.monotonic()
    gap = now - _last_hist_ts
    if gap < _MIN_HIST_GAP_SEC:
        time.sleep(_MIN_HIST_GAP_SEC - gap)
    _last_hist_ts = time.monotonic()


def _connect():
    """Return connected IB instance or None."""
    global _IB, _LAST_ERROR
    cfg = ibkr_config()
    if not cfg["enabled"]:
        _LAST_ERROR = "IBKR_ENABLED not set"
        return None
    try:
        from ib_insync import IB
    except ImportError:
        _LAST_ERROR = "ib_insync not installed (pip install ib_insync)"
        logger.warning(_LAST_ERROR)
        return None

    with _LOCK:
        if _IB is not None and _IB.isConnected():
            return _IB
        if _IB is not None:
            try:
                _IB.disconnect()
            except Exception:  # noqa: BLE001
                pass
            _IB = None

        ib = IB()
        try:
            # readonly=True: research-only; still honor TWS Read-Only API checkbox
            kwargs = dict(
                host=cfg["host"],
                port=cfg["port"],
                clientId=cfg["client_id"],
                timeout=cfg["timeout"],
            )
            # ib_insync supports readonly on connect in recent versions
            try:
                ib.connect(**kwargs, readonly=bool(cfg["readonly"]))
            except TypeError:
                ib.connect(**kwargs)
        except Exception as exc:  # noqa: BLE001
            _LAST_ERROR = f"connect failed {cfg['host']}:{cfg['port']}: {exc}"
            logger.warning("IBKR %s", _LAST_ERROR)
            try:
                ib.disconnect()
            except Exception:  # noqa: BLE001
                pass
            return None

        if not ib.isConnected():
            _LAST_ERROR = "connect returned but not connected"
            return None
        _IB = ib
        _LAST_ERROR = ""
        logger.info(
            "IBKR research connected %s:%s clientId=%s readonly=%s",
            cfg["host"],
            cfg["port"],
            cfg["client_id"],
            cfg["readonly"],
        )
        return _IB


def fetch_ibkr_ohlcv(
    symbol: str,
    *,
    interval: str = "1d",
    period: str = "1y",
    use_rth: bool = True,
) -> Dict[str, List[float]]:
    """Fetch OHLCV lists. Empty dict-like bars on failure (never raises for research)."""
    global _LAST_ERROR
    empty: Dict[str, List[float]] = {"close": [], "high": [], "low": [], "volume": []}
    sym = (symbol or "").upper().strip()
    if not sym:
        return empty

    cache_key = (sym, interval, period)
    if cache_key in _CACHE:
        return {k: list(v) for k, v in _CACHE[cache_key].items()}

    ib = _connect()
    if ib is None:
        return empty

    try:
        from ib_insync import Stock
    except ImportError:
        _LAST_ERROR = "ib_insync missing"
        return empty

    try:
        contract = Stock(sym, "SMART", "USD")
        with _LOCK:
            if not ib.isConnected():
                return empty
            qualified = ib.qualifyContracts(contract)
            if not qualified:
                _LAST_ERROR = f"qualifyContracts failed for {sym}"
                logger.warning("IBKR %s", _LAST_ERROR)
                return empty
            contract = qualified[0]
            _pace()
            bars = ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr=_map_period_duration(period),
                barSizeSetting=_map_bar_size(interval),
                whatToShow="TRADES",
                useRTH=use_rth,
                formatDate=1,
            )
    except Exception as exc:  # noqa: BLE001
        _LAST_ERROR = f"hist {sym}: {exc}"
        logger.warning("IBKR OHLCV failed %s: %s", sym, exc)
        # drop dead connection for next call
        if "connect" in str(exc).lower() or "not connected" in str(exc).lower():
            disconnect_ibkr()
        return empty

    if not bars:
        _LAST_ERROR = f"empty bars for {sym}"
        return empty

    result: Dict[str, List[float]] = {
        "close": [float(b.close) for b in bars],
        "high": [float(b.high) for b in bars],
        "low": [float(b.low) for b in bars],
        "volume": [float(b.volume) if b.volume is not None else 0.0 for b in bars],
        "open": [float(b.open) for b in bars],
    }
    _CACHE[cache_key] = result
    _LAST_ERROR = ""
    return {k: list(v) for k, v in result.items()}


def ping_ibkr() -> Dict[str, Any]:
    """Connectivity + one SPY bar sample for setup verification."""
    cfg = ibkr_config()
    out: Dict[str, Any] = {
        "enabled": cfg["enabled"],
        "host": cfg["host"],
        "port": cfg["port"],
        "client_id": cfg["client_id"],
        "readonly": cfg["readonly"],
        "ib_insync": False,
        "connected": False,
        "bars": 0,
        "last_close": None,
        "error": "",
    }
    try:
        import ib_insync  # noqa: F401

        out["ib_insync"] = True
    except ImportError:
        out["error"] = "ib_insync not installed"
        return out

    if not cfg["enabled"]:
        out["error"] = "Set IBKR_ENABLED=1"
        return out

    bars = fetch_ibkr_ohlcv("SPY", interval="1d", period="5d")
    out["connected"] = bool(bars.get("close"))
    out["bars"] = len(bars.get("close") or [])
    if out["bars"]:
        out["last_close"] = bars["close"][-1]
    else:
        out["error"] = last_ibkr_error() or "no bars"
    return out
