"""Shared scanned_list read/write used by trading_test + trading_agent."""

from __future__ import annotations

from pathlib import Path

from trading_agent.export.scanned_list import (
    build_scanned_list,
    load_scanned_list,
    publish_scanned_list,
    symbols_from_scanned_list,
    write_scanned_list,
)


def test_build_and_roundtrip(tmp_path: Path):
    doc = build_scanned_list(
        universe=["NVDA", "AMD", "SPY", "penny", "NVDA"],
        watchlist=["NVDA", "AMD"],
        play_symbols=["NVDA"],
        stay_in_cash=False,
        source_product="trading_test",
        source_phase="unit",
        trading_date="2026-08-12",
    )
    assert "PENNY" not in doc["universe"]
    assert doc["universe"][0] == "NVDA"
    assert "NVDA" in doc["play_symbols"]
    paths = write_scanned_list(doc, sync_dir=tmp_path, session_dir=tmp_path / "sess")
    assert paths
    assert (tmp_path / "scanned_list.json").is_file()
    assert (tmp_path / "auto_trade_scan_symbols.json").is_file()
    loaded = load_scanned_list(sync_dir=tmp_path, max_age_hours=None)
    assert loaded is not None
    assert loaded["watchlist"] == ["NVDA", "AMD"]
    syms = symbols_from_scanned_list(prefer="play_symbols", sync_dir=tmp_path, max_age_hours=None)
    assert syms == ["NVDA"]


def test_publish_scanned_list(tmp_path: Path):
    doc, paths = publish_scanned_list(
        universe=["QQQ", "IWM"],
        watchlist=["QQQ"],
        play_symbols=[],
        source_product="trading_agent",
        source_phase="desk_research",
        sync_dir=tmp_path,
    )
    assert paths
    assert doc["source_product"] == "trading_agent"
    assert doc["stay_in_cash"] is True
