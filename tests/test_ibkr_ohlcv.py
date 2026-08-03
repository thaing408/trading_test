"""IBKR research OHLCV mapping + provider preference (mocked; no TWS required)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from trading_agent.config import AgentConfig
from trading_agent.market_data.ibkr_ohlcv import (
    _map_bar_size,
    _map_period_duration,
    clear_ibkr_cache,
    disconnect_ibkr,
    fetch_ibkr_ohlcv,
    ibkr_config,
    ping_ibkr,
)
from trading_agent.market_data.provider import get_ohlcv, last_ohlcv_source, reset_ohlcv_cache


def setup_function() -> None:
    clear_ibkr_cache()
    disconnect_ibkr()
    reset_ohlcv_cache()


def test_map_period_duration():
    assert _map_period_duration("5d") == "5 D"
    assert _map_period_duration("1y") == "1 Y"
    assert _map_period_duration("60d") == "60 D"
    assert _map_period_duration("3mo") == "3 M"
    assert _map_period_duration("weird") == "1 Y"


def test_map_bar_size():
    assert _map_bar_size("1d") == "1 day"
    assert _map_bar_size("15m") == "15 mins"
    assert _map_bar_size("1h") == "1 hour"
    assert _map_bar_size("1m") == "1 min"


def test_ibkr_config_defaults(monkeypatch):
    monkeypatch.delenv("IBKR_ENABLED", raising=False)
    monkeypatch.delenv("IBKR_PORT", raising=False)
    cfg = ibkr_config()
    assert cfg["enabled"] is False
    assert cfg["port"] == 7496
    assert cfg["readonly"] is True


def test_ping_ibkr_disabled(monkeypatch):
    monkeypatch.delenv("IBKR_ENABLED", raising=False)
    out = ping_ibkr()
    assert out["enabled"] is False
    assert out["connected"] is False
    assert "IBKR_ENABLED" in out["error"]


def test_fetch_ibkr_returns_empty_when_disabled(monkeypatch):
    monkeypatch.delenv("IBKR_ENABLED", raising=False)
    bars = fetch_ibkr_ohlcv("SPY", period="5d")
    assert bars["close"] == []


def test_provider_prefers_ibkr_when_enabled(monkeypatch):
    monkeypatch.setenv("IBKR_ENABLED", "1")
    reset_ohlcv_cache()
    ibkr_bars = {
        "open": [100.0],
        "high": [101.0],
        "low": [99.0],
        "close": [100.5],
        "volume": [1e6],
    }
    cfg = AgentConfig(fixture_mode=False, use_live_data=True, market_data_provider="auto")
    with (
        patch(
            "trading_agent.market_data.ibkr_ohlcv.ibkr_available",
            return_value=True,
        ),
        patch(
            "trading_agent.market_data.ibkr_ohlcv.fetch_ibkr_ohlcv",
            return_value=ibkr_bars,
        ) as fetch,
        patch(
            "trading_agent.market_data.schwab_ohlcv.schwab_available",
            return_value=True,
        ),
        patch("trading_agent.market_data.schwab_ohlcv.fetch_schwab_ohlcv") as schwab,
        patch("trading_agent.market_data.provider._yfinance_ohlcv") as yf,
    ):
        bars = get_ohlcv("SPY", cfg, interval="1d", period="5d")
    assert bars["close"] == [100.5]
    assert last_ohlcv_source("SPY") == "ibkr"
    fetch.assert_called_once()
    schwab.assert_not_called()
    yf.assert_not_called()


def test_provider_ibkr_fallback_to_schwab(monkeypatch):
    monkeypatch.setenv("IBKR_ENABLED", "1")
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
            "trading_agent.market_data.ibkr_ohlcv.ibkr_available",
            return_value=True,
        ),
        patch(
            "trading_agent.market_data.ibkr_ohlcv.fetch_ibkr_ohlcv",
            return_value={"close": [], "high": [], "low": [], "volume": []},
        ),
        patch(
            "trading_agent.market_data.schwab_ohlcv.schwab_available",
            return_value=True,
        ),
        patch(
            "trading_agent.market_data.schwab_ohlcv.fetch_schwab_ohlcv",
            return_value=schwab_bars,
        ),
        patch("trading_agent.market_data.provider._yfinance_ohlcv") as yf,
    ):
        bars = get_ohlcv("MSFT", cfg, interval="1d", period="1y")
    assert bars["close"] == [1.5]
    assert last_ohlcv_source("MSFT") == "schwab"
    yf.assert_not_called()


def test_provider_ibkr_only_fail_closed(monkeypatch):
    monkeypatch.setenv("IBKR_ENABLED", "1")
    reset_ohlcv_cache()
    cfg = AgentConfig(fixture_mode=False, use_live_data=True, market_data_provider="ibkr")
    with (
        patch(
            "trading_agent.market_data.ibkr_ohlcv.ibkr_available",
            return_value=True,
        ),
        patch(
            "trading_agent.market_data.ibkr_ohlcv.fetch_ibkr_ohlcv",
            return_value={"close": [], "high": [], "low": [], "volume": []},
        ),
        patch("trading_agent.market_data.provider._yfinance_ohlcv") as yf,
    ):
        bars = get_ohlcv("QQQ", cfg, interval="1d", period="5d")
    assert bars["close"] == []
    # Strict ibkr pref must not call yfinance
    yf.assert_not_called()


def test_provider_skips_ibkr_when_not_enabled(monkeypatch):
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
            "trading_agent.market_data.ibkr_ohlcv.fetch_ibkr_ohlcv",
        ) as fetch_ibkr,
        patch(
            "trading_agent.market_data.schwab_ohlcv.schwab_available",
            return_value=True,
        ),
        patch(
            "trading_agent.market_data.schwab_ohlcv.fetch_schwab_ohlcv",
            return_value=schwab_bars,
        ),
        patch("trading_agent.market_data.provider._yfinance_ohlcv") as yf,
    ):
        bars = get_ohlcv("AAPL", cfg, interval="1d", period="1y")
    assert bars["close"] == [1.5]
    assert last_ohlcv_source("AAPL") == "schwab"
    fetch_ibkr.assert_not_called()
    yf.assert_not_called()


def test_fetch_ibkr_from_mock_bars(monkeypatch):
    """fetch_ibkr_ohlcv with mocked connect + ib_insync Stock/history."""
    monkeypatch.setenv("IBKR_ENABLED", "1")
    clear_ibkr_cache()
    disconnect_ibkr()

    bar = MagicMock()
    bar.open = 10.0
    bar.high = 11.0
    bar.low = 9.0
    bar.close = 10.5
    bar.volume = 1000

    mock_ib = MagicMock()
    mock_ib.isConnected.return_value = True
    mock_ib.qualifyContracts.return_value = [MagicMock()]
    mock_ib.reqHistoricalData.return_value = [bar]

    fake_ib_insync = MagicMock()
    fake_ib_insync.Stock = MagicMock(return_value=MagicMock())

    with (
        patch("trading_agent.market_data.ibkr_ohlcv._connect", return_value=mock_ib),
        patch.dict("sys.modules", {"ib_insync": fake_ib_insync}),
    ):
        bars = fetch_ibkr_ohlcv("SPY", interval="1d", period="5d")

    assert bars.get("close") == [10.5]
    assert bars.get("high") == [11.0]
    mock_ib.reqHistoricalData.assert_called_once()
