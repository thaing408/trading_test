"""Schwab Trader API price history → OHLCV lists for strength gates / technicals."""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

MARKET_BASE = "https://api.schwabapi.com/marketdata/v1"
OAUTH_URL = "https://api.schwabapi.com/v1/oauth/token"
DEFAULT_TOKEN_PATH = Path.home() / ".schwab-mcp" / "token.json"

# In-process cache: (symbol, interval, period) -> ohlcv dict
_CACHE: dict[tuple[str, str, str], Dict[str, List[float]]] = {}


def token_path() -> Path:
    raw = os.getenv("SCHWAB_TOKEN_PATH", "").strip()
    if raw:
        return Path(raw).expanduser()
    return DEFAULT_TOKEN_PATH


def schwab_available() -> bool:
    """True when token file exists with credentials we can use."""
    path = token_path()
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return bool(data.get("access_token") or data.get("refresh_token"))


def _load_token_file() -> dict:
    path = token_path()
    with open(path) as f:
        return json.load(f)


def _save_token_file(data: dict) -> None:
    path = token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _basic_auth(client_id: str, client_secret: str) -> str:
    creds = f"{client_id}:{client_secret}"
    return "Basic " + base64.b64encode(creds.encode()).decode()


def _get_access_token() -> str:
    data = _load_token_file()
    access = data.get("access_token") or ""
    expires_at = float(data.get("expires_at") or 0)
    # 90s buffer — strength loop may run many symbols
    if access and time.time() < (expires_at - 90):
        return access

    refresh = data.get("refresh_token")
    client_id = data.get("client_id") or os.getenv("SCHWAB_CLIENT_ID", "")
    client_secret = data.get("client_secret") or os.getenv("SCHWAB_CLIENT_SECRET", "")
    if not refresh or not client_id or not client_secret:
        if access:
            logger.warning("Schwab token near expiry and cannot refresh; trying existing access token")
            return access
        raise RuntimeError("Schwab token missing refresh credentials")

    resp = requests.post(
        OAUTH_URL,
        headers={
            "Authorization": _basic_auth(client_id, client_secret),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": "refresh_token", "refresh_token": refresh},
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    now = time.time()
    data["access_token"] = payload["access_token"]
    if payload.get("refresh_token"):
        data["refresh_token"] = payload["refresh_token"]
        data["refresh_issued_at"] = now
    data["expires_at"] = now + float(payload.get("expires_in", 1800))
    data["token_type"] = payload.get("token_type", "Bearer")
    data["client_id"] = client_id
    data["client_secret"] = client_secret
    _save_token_file(data)
    logger.info("Schwab access token refreshed for market data")
    return data["access_token"]


def _parse_period(period: str) -> Tuple[str, int]:
    """Map yfinance-style period to Schwab (periodType, period)."""
    p = (period or "1y").strip().lower()
    if p.endswith("y") and p[:-1].isdigit():
        return "year", int(p[:-1])
    if p.endswith("mo") and p[:-2].isdigit():
        return "month", int(p[:-2])
    if p.endswith("m") and not p.endswith("mo") and p[:-1].isdigit():
        # treat bare 'm' as months when not 'mo' (yfinance uses 1mo, 3mo)
        return "month", int(p[:-1])
    if p.endswith("d") and p[:-1].isdigit():
        return "day", int(p[:-1])
    if p == "ytd":
        return "ytd", 1
    if p == "max":
        return "year", 20
    return "year", 1


def _map_interval(interval: str, period: str) -> dict[str, Any]:
    """Build Schwab pricehistory query params for a yfinance-like interval/period."""
    interval = (interval or "1d").strip().lower()
    period_type, period_n = _parse_period(period)

    if interval in ("1d", "d", "day", "daily"):
        # Daily: prefer year/month periods
        if period_type == "day":
            # Schwab daily often wants month/year; approximate days as months
            period_type, period_n = "month", max(1, (period_n + 20) // 21)
        return {
            "periodType": period_type if period_type != "ytd" else "ytd",
            "period": period_n if period_type != "ytd" else 1,
            "frequencyType": "daily",
            "frequency": 1,
        }

    # Intraday minute bars — Schwab allows 1,5,10,15,30 only
    freq_map = {
        "1m": 1,
        "5m": 5,
        "10m": 10,
        "15m": 15,
        "30m": 30,
        "1h": 30,  # closest supported; consumers use as intraday series
        "60m": 30,
        "90m": 30,
    }
    frequency = freq_map.get(interval, 30)
    # Minute history is requested with periodType=day
    if period_type in ("year", "month", "ytd"):
        day_period = 10 if period_type == "year" else min(10, max(1, period_n * 2))
    else:
        day_period = max(1, min(period_n, 10))
    return {
        "periodType": "day",
        "period": day_period,
        "frequencyType": "minute",
        "frequency": frequency,
    }


def _candles_to_ohlcv(candles: List[dict]) -> Dict[str, List[float]]:
    ordered = sorted(candles, key=lambda c: c.get("datetime") or 0)
    out: Dict[str, List[float]] = {
        "open": [],
        "high": [],
        "low": [],
        "close": [],
        "volume": [],
    }
    for c in ordered:
        if c.get("close") is None:
            continue
        out["open"].append(float(c.get("open") or c["close"]))
        out["high"].append(float(c.get("high") or c["close"]))
        out["low"].append(float(c.get("low") or c["close"]))
        out["close"].append(float(c["close"]))
        out["volume"].append(float(c.get("volume") or 0))
    return out


def _fetch_pricehistory_candles(
    symbol: str,
    interval: str = "1d",
    period: str = "1y",
    *,
    extended_hours: bool = False,
) -> List[dict]:
    """Raw Schwab pricehistory candles (datetime ms + OHLCV)."""
    sym = symbol.strip().upper()
    params = _map_interval(interval, period)
    params.update(
        {
            "symbol": sym,
            "needExtendedHoursData": "true" if extended_hours else "false",
            "needPreviousClose": "true",
        }
    )
    token = _get_access_token()
    resp = requests.get(
        f"{MARKET_BASE}/pricehistory",
        params=params,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=45,
    )
    if resp.status_code == 401:
        # force refresh once
        data = _load_token_file()
        data["expires_at"] = 0
        _save_token_file(data)
        token = _get_access_token()
        resp = requests.get(
            f"{MARKET_BASE}/pricehistory",
            params=params,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=45,
        )
    resp.raise_for_status()
    payload = resp.json()
    return list(payload.get("candles") or [])


def fetch_schwab_ohlcv(
    symbol: str,
    interval: str = "1d",
    period: str = "1y",
    *,
    use_cache: bool = True,
) -> Dict[str, List[float]]:
    """
    Fetch OHLCV from Schwab Market Data API.

    Returns empty lists on hard failure (caller may fall back).
    """
    sym = symbol.strip().upper()
    cache_key = (sym, interval, period)
    if use_cache and cache_key in _CACHE:
        return {k: list(v) for k, v in _CACHE[cache_key].items()}

    candles = _fetch_pricehistory_candles(sym, interval=interval, period=period)
    ohlcv = _candles_to_ohlcv(candles)
    if not ohlcv["close"]:
        raise RuntimeError(f"Schwab returned no candles for {sym} ({interval}/{period})")
    if use_cache:
        _CACHE[cache_key] = ohlcv
    return {k: list(v) for k, v in ohlcv.items()}


def fetch_schwab_ohlcv_dataframe(
    symbol: str,
    interval: str = "1m",
    period: str = "10d",
    *,
    extended_hours: bool = True,
):
    """
    Schwab/TOS price history as a pandas DataFrame (ET index).

    Columns: Open, High, Low, Close, Volume — same shape as yfinance history.
    """
    import pandas as pd

    candles = _fetch_pricehistory_candles(
        symbol,
        interval=interval,
        period=period,
        extended_hours=extended_hours,
    )
    if not candles:
        raise RuntimeError(f"Schwab returned no candles for {symbol} ({interval}/{period})")

    rows = []
    for c in sorted(candles, key=lambda x: x.get("datetime") or 0):
        if c.get("close") is None:
            continue
        ms = c.get("datetime")
        if ms is None:
            continue
        # Schwab timestamps are epoch ms in US/Eastern for equities
        ts = pd.Timestamp(int(ms), unit="ms", tz="America/New_York")
        rows.append(
            {
                "Datetime": ts,
                "Open": float(c.get("open") or c["close"]),
                "High": float(c.get("high") or c["close"]),
                "Low": float(c.get("low") or c["close"]),
                "Close": float(c["close"]),
                "Volume": float(c.get("volume") or 0),
            }
        )
    if not rows:
        raise RuntimeError(f"Schwab candles empty after parse for {symbol}")
    df = pd.DataFrame(rows).set_index("Datetime")
    # drop duplicate timestamps keep last
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def clear_schwab_cache() -> None:
    _CACHE.clear()
