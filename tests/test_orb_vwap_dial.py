"""ORB opening-range window dial (research sleeve)."""

from __future__ import annotations

from trading_agent.sleeves.orb_vwap import (
    compare_orb_windows,
    format_orb_compare_report,
    or_bar_count,
    run_orb_vwap_backtest,
)


def test_or_bar_count():
    assert or_bar_count(15) == 1
    assert or_bar_count(30) == 2
    assert or_bar_count(45) == 3
    assert or_bar_count(60) == 4
    assert or_bar_count(5) == 1  # approx on 15m feed


def test_backtest_metadata_or_minutes(monkeypatch):
    monkeypatch.setattr(
        "trading_agent.sleeves.orb_vwap.run_orb_vwap_symbol",
        lambda *a, **k: [],
    )
    r15 = run_orb_vwap_backtest(symbols=["QQQ"], period="5d", or_minutes=15)
    r30 = run_orb_vwap_backtest(symbols=["QQQ"], period="5d", or_minutes=30)
    assert r15.metadata["or_minutes"] == 15
    assert r15.metadata["or_bars"] == 1
    assert r30.metadata["or_minutes"] == 30
    assert r30.metadata["or_bars"] == 2
    assert "30m" in r30.assumptions[0] or "30" in r30.assumptions[0]


def test_compare_report_side_by_side(monkeypatch):
    monkeypatch.setattr(
        "trading_agent.sleeves.orb_vwap.run_orb_vwap_symbol",
        lambda *a, **k: [],
    )
    cmp = compare_orb_windows(
        symbols=["QQQ"], period="5d", or_minutes_list=(15, 30)
    )
    text = format_orb_compare_report(cmp)
    assert "ORB window dial compare" in text
    assert "| 15 |" in text
    assert "| 30 |" in text
    assert "Research dial only" in text
