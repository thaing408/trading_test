"""Authoritative source → phase mapping (mirrors docs/provider_phase_mapping.md)."""

from __future__ import annotations

from typing import Dict, List

# Seven desk phase ids (session.schedule.DeskPhaseKind values)
PHASE_IDS = (
    "intelligence",
    "research",
    "cio_approval",
    "preopen",
    "intraday",
    "performance",
    "cio_review",
)

# source_id -> metadata used by config and docs
SOURCE_CATALOG: Dict[str, dict] = {
    "yfinance": {
        "url": "https://github.com/ranaroussi/yfinance",
        "role": ("market_data", "news", "options"),
        "phases": ("intelligence", "research", "preopen", "intraday", "performance"),
        "brokerage": False,
    },
    "pandas_datareader": {
        "url": "https://pandas-datareader.readthedocs.io/en/latest/",
        "role": ("market_data",),
        "phases": ("intelligence", "performance"),
        "brokerage": False,
    },
    "ibkr_tws": {
        "url": "https://interactivebrokers.github.io/tws-api/",
        "role": ("brokerage",),
        "phases": ("preopen", "intraday", "performance"),
        "brokerage": True,
    },
    "alpha_vantage": {
        "url": "https://github.com/RomelTorres/alpha_vantage",
        "role": ("market_data",),
        "phases": ("intelligence", "research"),
        "brokerage": False,
    },
    "nasdaq_data_link": {
        "url": "https://github.com/Nasdaq/data-link-python",
        "role": ("market_data",),
        "phases": ("intelligence", "research"),
        "brokerage": False,
    },
    "twelve_data": {
        "url": "https://github.com/twelvedata/twelvedata-python",
        "role": ("market_data",),
        "phases": ("intelligence", "research", "preopen"),
        "brokerage": False,
    },
    "massive": {
        "url": "https://github.com/massive-com/client-python",
        "role": ("market_data",),
        "phases": ("intelligence", "research", "intraday"),
        "brokerage": False,
    },
    "tradier": {
        "url": "https://documentation.tradier.com/",
        "role": ("market_data", "options", "brokerage"),
        "phases": ("research", "preopen", "intraday", "performance"),
        "brokerage": True,
    },
    "alpaca": {
        "url": "https://github.com/alpacahq/alpaca-py",
        "role": ("brokerage", "market_data"),
        "phases": ("preopen", "intraday", "performance"),
        "brokerage": True,
    },
    "finnhub": {
        "url": "https://github.com/Finnhub-Stock-API/finnhub-python",
        "role": ("market_data", "news"),
        "phases": ("intelligence", "research"),
        "brokerage": False,
    },
    "marketstack": {
        "url": "https://marketstack.com/documentation",
        "role": ("market_data",),
        "phases": ("intelligence", "research"),
        "brokerage": False,
    },
    "tiingo": {
        "url": "https://www.tiingo.com/documentation",
        "role": ("market_data", "news"),
        "phases": ("intelligence", "research"),
        "brokerage": False,
    },
}

# Convenience: phase -> list of source ids
PHASE_SOURCE_MAP: Dict[str, List[str]] = {pid: [] for pid in PHASE_IDS}
for _sid, meta in SOURCE_CATALOG.items():
    for phase in meta["phases"]:
        PHASE_SOURCE_MAP.setdefault(phase, []).append(_sid)


def list_sources_for_phase(phase: str) -> List[str]:
    return list(PHASE_SOURCE_MAP.get(phase, []))


def list_brokerage_sources() -> List[str]:
    return [sid for sid, meta in SOURCE_CATALOG.items() if meta.get("brokerage")]


def list_market_data_sources() -> List[str]:
    return [
        sid
        for sid, meta in SOURCE_CATALOG.items()
        if "market_data" in meta.get("role", ())
    ]
