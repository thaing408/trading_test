"""Tests for plan context and positions loading defaults."""

from __future__ import annotations

import json
from pathlib import Path

from trading_agent.intraday.config import IntradayConfig
from trading_agent.intraday.pipeline import run_intraday_pipeline
from trading_agent.intraday.plan_loader import load_plan_context, load_positions
from trading_agent.session.play_formatter import format_intraday_plays

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def test_load_positions_live_without_path_returns_empty():
    positions = load_positions(None, fixture_mode=False)
    assert positions == []


def test_load_positions_fixture_without_path_uses_fixture_file():
    positions = load_positions(None, fixture_mode=True)
    symbols = {p.symbol for p in positions}
    assert symbols == {"NVDA", "AAPL", "TSLA"}


def test_load_plan_context_live_without_path_returns_neutral_defaults():
    context = load_plan_context(None, fixture_mode=False)
    assert context["market_regime"] == "neutral"
    assert context["top_watchlist"] == []


def test_intraday_live_default_watchlist_scout_without_positions():
    config = IntradayConfig(
        fixture_mode=False,
        use_live_data=False,
        plan_file=str(FIXTURE_DIR / "daily_plan_context.json"),
        positions_file=None,
        session_file=str(FIXTURE_DIR / "intraday_session.json"),
        watch_symbols=["NVDA", "AAPL", "TSLA"],
    )
    report = run_intraday_pipeline(config)
    assert report.no_open_positions
    text = format_intraday_plays(report, cycle=1)
    assert "Watchlist scout" in text
    assert "NVDA" in text
    assert "AAPL" in text