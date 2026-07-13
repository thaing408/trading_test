"""Tests for multi-provider registry, config, and fail-closed paths."""

from __future__ import annotations

import os

import pytest

from trading_agent.collectors.market import collect_market_snapshot
from trading_agent.collectors.news import collect_news_catalysts
from trading_agent.config import AgentConfig
from trading_agent.providers.base import ProviderFetchResult
from trading_agent.providers.brokerage import (
    fetch_alpaca_positions,
    fetch_tradier_positions,
    load_broker_positions,
)
from trading_agent.providers.config import ProviderConfig
from trading_agent.providers.news_providers import fetch_news_multi
from trading_agent.providers.quotes import fetch_quotes_multi
from trading_agent.providers.registry import (
    PHASE_IDS,
    SOURCE_CATALOG,
    list_brokerage_sources,
    list_sources_for_phase,
)


OBJECTIVE_SOURCES = {
    "yfinance",
    "pandas_datareader",
    "ibkr_tws",
    "alpha_vantage",
    "nasdaq_data_link",
    "twelve_data",
    "massive",
    "tradier",
    "alpaca",
    "finnhub",
    "marketstack",
    "tiingo",
}


def test_registry_covers_all_objective_sources_and_seven_phases():
    assert set(SOURCE_CATALOG.keys()) == OBJECTIVE_SOURCES
    for phase in PHASE_IDS:
        assert phase in (
            "intelligence",
            "research",
            "cio_approval",
            "preopen",
            "intraday",
            "performance",
            "cio_review",
        )
    # Every source appears on at least one phase (except pure CIO consumers)
    for sid, meta in SOURCE_CATALOG.items():
        assert meta["phases"], f"{sid} has no phases"
        assert meta["url"]
        assert meta["role"]
    # Brokerage classification
    brokers = set(list_brokerage_sources())
    assert "alpaca" in brokers
    assert "tradier" in brokers
    assert "ibkr_tws" in brokers
    assert "yfinance" not in brokers
    # Intelligence has multi market-data sources
    intel = list_sources_for_phase("intelligence")
    assert "yfinance" in intel
    assert "finnhub" in intel
    assert "tiingo" in intel


def test_provider_config_missing_keys_not_configured(monkeypatch):
    for key in (
        "FINNHUB_API_KEY",
        "ALPHA_VANTAGE_API_KEY",
        "TWELVE_DATA_API_KEY",
        "TIINGO_API_KEY",
        "MARKETSTACK_API_KEY",
        "ALPACA_API_KEY",
        "ALPACA_SECRET_KEY",
        "TRADIER_ACCESS_TOKEN",
    ):
        monkeypatch.delenv(key, raising=False)
    cfg = ProviderConfig.from_env()
    assert cfg.is_configured("yfinance") is True
    assert cfg.is_configured("finnhub") is False
    assert cfg.is_configured("alpha_vantage") is False
    assert cfg.is_configured("alpaca") is False
    assert cfg.is_configured("tradier") is False


def test_fetch_quotes_multi_unavailable_without_keys(monkeypatch):
    for key in (
        "FINNHUB_API_KEY",
        "ALPHA_VANTAGE_API_KEY",
        "TWELVE_DATA_API_KEY",
        "TIINGO_API_KEY",
        "MARKETSTACK_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    result = fetch_quotes_multi(["AAPL", "MSFT"], ProviderConfig.from_env())
    assert result.ok is False
    assert result.source == "unavailable"
    assert result.quotes == {}
    assert result.errors


def test_fetch_news_multi_unavailable_without_keys(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.delenv("TIINGO_API_KEY", raising=False)
    result = fetch_news_multi(["NVDA"], ProviderConfig.from_env())
    assert result.ok is False
    assert result.source == "unavailable"
    assert result.headlines == []


def test_brokerage_fail_closed_without_credentials(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    monkeypatch.delenv("TRADIER_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("TRADIER_ACCOUNT_ID", raising=False)
    cfg = ProviderConfig.from_env()
    alpaca = fetch_alpaca_positions(cfg)
    tradier = fetch_tradier_positions(cfg)
    combined = load_broker_positions(cfg)
    assert alpaca.ok is False and alpaca.source == "alpaca"
    assert tradier.ok is False
    assert combined.ok is False
    assert combined.positions == []
    assert "unavailable" in combined.source or combined.errors


def test_live_news_collector_no_fixture_fill_without_feeds(monkeypatch):
    """Live path with empty yfinance + no keys must be unavailable, not fixture."""
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.delenv("TIINGO_API_KEY", raising=False)
    monkeypatch.delenv("FMP_API_KEY", raising=False)

    def _empty_yf(symbols):
        return []

    monkeypatch.setattr(
        "trading_agent.collectors.news._fetch_yfinance_news",
        _empty_yf,
    )
    news = collect_news_catalysts(
        AgentConfig(fixture_mode=False, use_live_data=True),
        ["NVDA", "AAPL"],
    )
    assert news.source == "unavailable"
    assert news.items == []
    assert "NVDA beats" not in " ".join(i.headline for i in news.items)


def test_fixture_market_still_offline():
    snap = collect_market_snapshot(AgentConfig(fixture_mode=True, use_live_data=False))
    assert snap.source == "fixture"
    assert snap.futures


def test_mapping_doc_exists_and_lists_sources():
    from pathlib import Path

    doc = Path(__file__).resolve().parents[1] / "docs" / "provider_phase_mapping.md"
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    for sid in OBJECTIVE_SOURCES:
        assert sid.replace("_", "") in text.replace("_", "") or sid in text
    for phase in PHASE_IDS:
        assert phase in text


def test_finnhub_quote_adapter_parses_payload(monkeypatch):
    """Drive real shipped quote function with mocked HTTP."""
    from trading_agent.providers import quotes as quotes_mod

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"c": 100.0, "pc": 95.0}

    monkeypatch.setattr(quotes_mod, "http_get", lambda *a, **k: FakeResp())
    q = quotes_mod.fetch_finnhub_quote("AAPL", "test-key")
    assert q is not None
    assert q.source == "finnhub"
    assert q.last == 100.0
    assert q.change_pct == pytest.approx(5.26, abs=0.05)


def test_alpha_vantage_quote_adapter_parses_payload(monkeypatch):
    from trading_agent.providers import quotes as quotes_mod

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "Global Quote": {
                    "05. price": "200.0",
                    "10. change percent": "1.50%",
                }
            }

    monkeypatch.setattr(quotes_mod, "http_get", lambda *a, **k: FakeResp())
    q = quotes_mod.fetch_alpha_vantage_quote("MSFT", "demo")
    assert q is not None
    assert q.source == "alpha_vantage"
    assert q.last == 200.0
    assert q.change_pct == 1.5
