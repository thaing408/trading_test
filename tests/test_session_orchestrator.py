"""Tests for full session orchestrator fixture output."""

from __future__ import annotations

from datetime import date

from trading_agent.intraday.plan_loader import load_positions
from trading_agent.session.config import SessionConfig
from trading_agent.session.orchestrator import run_session


def test_fixture_session_contains_premarket_and_intraday_plays():
    config = SessionConfig(
        fixture_mode=True,
        dry_run=True,
        trading_date=date(2026, 7, 9),
        intraday_cycles=1,
        wait_for_schedule=False,
    )
    result = run_session(config)

    assert result.premarket_message
    assert "Bias:" in result.premarket_message
    assert result.intraday_messages
    intraday = result.intraday_messages[0]
    assert "Intraday Update" in intraday
    assert any(
        term in intraday
        for term in ("Exit", "Hold", "Move Stop Loss", "Watchlist scout", "Position actions")
    )
    assert any(sym in intraday for sym in ("NVDA", "AAPL", "TSLA"))
    assert result.schedule_log
    assert "2026-07-09" in result.schedule_log
    assert result.plan_context_path


def test_live_session_default_has_no_positions():
    """Tomorrow's `session --date` without --positions must not load fixture book."""
    assert load_positions(None, fixture_mode=False) == []