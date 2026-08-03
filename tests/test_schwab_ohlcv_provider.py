"""Schwab OHLCV mapping + provider fallback behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from trading_agent.config import AgentConfig
from trading_agent.market_data.provider import get_ohlcv, last_ohlcv_source, reset_ohlcv_cache
from trading_agent.market_data.schwab_ohlcv import _map_interval, _candles_to_ohlcv


def test_map_interval_daily_year():
    p = _map_interval("1d", "1y")
    assert p["periodType"] == "year"
    assert p["period"] == 1
    assert p["frequencyType"] == "daily"


def test_map_interval_minute_for_intraday():
    p = _map_interval("15m", "5d")
    assert p["periodType"] == "day"
    assert p["frequencyType"] == "minute"
    assert p["frequency"] == 15
    p1h = _map_interval("1h", "10d")
    assert p1h["frequency"] == 30  # closest Schwab minute freq


def test_candles_to_ohlcv_sorts():
    candles = [
        {"datetime": 200, "open": 2, "high": 3, "low": 1, "close": 2.5, "volume": 10},
        {"datetime": 100, "open": 1, "high": 1.5, "low": 0.5, "close": 1.2, "volume": 5},
    ]
    o = _candles_to_ohlcv(candles)
    assert o["close"] == [1.2, 2.5]
    assert o["volume"] == [5.0, 10.0]


def test_provider_prefers_schwab_when_available(monkeypatch):
    # Without IBKR_ENABLED, auto chain is Schwab → yfinance
    monkeypatch.delenv("IBKR_ENABLED", raising=False)
    reset_ohlcv_cache()
    schwab_bars = {
        "open": [1.0],
        "high": [2.0],
        "low": [0.5],
        "close": [1.5],
        "volume": [100.0],
    }
    cfg = AgentConfig(fixture_mode=False, use_live_data=True, market_data_provider="auto")
    with (
        patch(
            "trading_agent.market_data.schwab_ohlcv.schwab_available",
            return_value=True,
        ),
        patch(
            "trading_agent.market_data.schwab_ohlcv.fetch_schwab_ohlcv",
            return_value=schwab_bars,
        ) as fetch,
        patch("trading_agent.market_data.provider._yfinance_ohlcv") as yf,
    ):
        bars = get_ohlcv("MSFT", cfg, interval="1d", period="1y")
    assert bars["close"] == [1.5]
    assert last_ohlcv_source("MSFT") == "schwab"
    fetch.assert_called_once()
    yf.assert_not_called()


def test_provider_falls_back_to_yfinance_on_schwab_error(monkeypatch):
    monkeypatch.delenv("IBKR_ENABLED", raising=False)
    reset_ohlcv_cache()
    cfg = AgentConfig(fixture_mode=False, use_live_data=True, market_data_provider="auto")
    yf_bars = {"close": [10.0], "high": [11.0], "low": [9.0], "volume": [1.0], "open": [10.0]}
    with (
        patch(
            "trading_agent.market_data.schwab_ohlcv.schwab_available",
            return_value=True,
        ),
        patch(
            "trading_agent.market_data.schwab_ohlcv.fetch_schwab_ohlcv",
            side_effect=RuntimeError("boom"),
        ),
        patch(
            "trading_agent.market_data.provider._yfinance_ohlcv",
            return_value=yf_bars,
        ),
    ):
        bars = get_ohlcv("AMZN", cfg, interval="1d", period="1y")
    assert bars["close"] == [10.0]
    assert last_ohlcv_source("AMZN") == "yfinance"


def test_fixture_mode_unchanged():
    reset_ohlcv_cache()
    cfg = AgentConfig(fixture_mode=True, use_live_data=False)
    bars = get_ohlcv("NVDA", cfg, interval="1d", period="1y")
    assert bars.get("close")  # fixture has NVDA
    assert last_ohlcv_source("NVDA") == "fixture"
