"""Expanded screener universe + scan-tier floors (more candidates, tight trade path)."""

from __future__ import annotations

from pathlib import Path

from trading_agent.collectors.screener import _passes_scan_floors
from trading_agent.config import AgentConfig, ScreenerConfig
from trading_agent.screener.universe import (
    CORE_LIQUID,
    default_expanded_universe,
    load_symbols_from_file,
    resolve_screener_symbols,
)


def test_expanded_universe_larger_than_core():
    expanded = default_expanded_universe()
    assert len(expanded) >= 60
    assert len(expanded) > len(CORE_LIQUID)
    assert "NVDA" in expanded
    assert "AVGO" in expanded
    assert "XLV" in expanded
    # de-duped
    assert len(expanded) == len(set(expanded))


def test_resolve_symbols_from_env_list():
    got = resolve_screener_symbols(
        ["ZZZ"],
        env_symbols="AAPL, MSFT ; NVDA",
        env_file="",
    )
    assert got == ["AAPL", "MSFT", "NVDA"]


def test_resolve_symbols_from_file(tmp_path: Path):
    p = tmp_path / "syms.txt"
    p.write_text("# comment\nTSLA\nAMD,JPM\n", encoding="utf-8")
    got = resolve_screener_symbols(None, env_symbols="", env_file=str(p))
    assert got == ["TSLA", "AMD", "JPM"]


def test_agent_config_default_screener_is_expanded():
    cfg = AgentConfig()
    assert len(cfg.screener.symbols) >= 60
    assert cfg.screener.min_relative_volume <= 1.5
    assert cfg.screener.min_avg_daily_volume <= 1_000_000
    assert cfg.risk.min_relative_volume >= 2.0  # trade path still tight
    assert cfg.strength_mode == "soft"
    assert cfg.risk.top_watchlist_size >= 15


def test_scan_floors_keep_mild_rvol_by_default():
    sc = ScreenerConfig(hard_rvol_filter=False, min_relative_volume=1.2)
    ok, _ = _passes_scan_floors(
        price=50.0,
        avg_vol=1_500_000,
        rel_vol=0.9,  # below scan RVOL but hard_rvol off
        market_cap=5e9,
        oi=500,
        spread_pct=2.0,
        sc=sc,
    )
    assert ok is True


def test_scan_floors_hard_drop_micro_illiquid():
    sc = ScreenerConfig(min_avg_daily_volume=1_000_000, hard_adv_fraction=0.15)
    ok, reason = _passes_scan_floors(
        price=50.0,
        avg_vol=50_000,  # far below hard ADV
        rel_vol=3.0,
        market_cap=5e9,
        oi=5000,
        spread_pct=1.0,
        sc=sc,
    )
    assert ok is False
    assert "ADV" in reason or "hard" in reason.lower()


def test_load_symbols_from_file_helper(tmp_path: Path):
    p = tmp_path / "u.txt"
    p.write_text("SPY QQQ\nAAPL\n", encoding="utf-8")
    assert load_symbols_from_file(p) == ["SPY", "QQQ", "AAPL"]
