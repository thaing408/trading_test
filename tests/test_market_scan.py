"""Desk-universe market scan export (pulse / Discord)."""

from __future__ import annotations

from unittest.mock import patch

from trading_agent.export.market_scan import (
    MarketScanResult,
    MoverRow,
    format_market_scan_block,
    run_market_scan,
)
from trading_agent.screener.universe import default_expanded_universe, resolve_screener_symbols


def test_resolve_screener_symbols_default_is_expanded():
    syms = resolve_screener_symbols()
    expanded = default_expanded_universe()
    assert len(syms) >= 20
    assert set(syms) == set(expanded) or len(syms) >= len(expanded) * 0.5


def test_run_market_scan_uses_universe_and_ranks(monkeypatch):
    uni = ["AAA", "BBB", "CCC", "DDD"]

    def fake_batch(symbols):
        assert symbols == uni
        rows = [
            MoverRow("AAA", 5.0, 10.0, "Technology"),
            MoverRow("BBB", -3.0, 20.0, "Energy"),
            MoverRow("CCC", 1.0, 15.0, "Financials"),
            MoverRow("DDD", -1.5, 8.0, "Consumer"),
        ]
        return rows, []

    with patch("trading_agent.export.market_scan.resolve_screener_symbols", return_value=uni):
        with patch("trading_agent.export.market_scan._batch_day_changes", side_effect=fake_batch):
            res = run_market_scan(top_n=2)
    assert res.universe_size == 4
    assert res.scanned == 4
    assert [r.symbol for r in res.gainers] == ["AAA", "CCC"]
    assert [r.symbol for r in res.losers] == ["BBB", "DDD"]
    text = format_market_scan_block(res)
    assert "desk universe" in text
    assert "AAA" in text and "BBB" in text


def test_format_market_scan_empty():
    res = MarketScanResult(universe_size=10, scanned=0)
    text = format_market_scan_block(res)
    assert "none" in text.lower() or "Gainers" in text
