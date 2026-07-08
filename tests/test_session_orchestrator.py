"""Tests for full session orchestrator fixture output."""

from __future__ import annotations

from datetime import date

from trading_agent.intraday.plan_loader import load_positions
from trading_agent.session.config import SessionConfig
from trading_agent.session.orchestrator import run_session


REQUIRED_TEAMS = [
    "Market Intelligence Team",
    "Trading Research Team",
    "Chief Investment Officer (Final Approval)",
    "Trading Desk (Pre-Open Check)",
    "Trading Desk — cycle 1",
    "Performance & Learning Team",
    "Chief Investment Officer Daily Review",
]


def test_fixture_session_contains_all_desk_phases(tmp_path):
    config = SessionConfig(
        fixture_mode=True,
        dry_run=True,
        trading_date=date(2026, 7, 9),
        intraday_cycles=1,
        wait_for_schedule=False,
        session_dir=tmp_path,
    )
    result = run_session(config)

    assert result.phase_messages.get("intelligence")
    assert result.phase_messages.get("research")
    assert result.phase_messages.get("cio_approval")
    assert result.phase_messages.get("preopen")
    assert result.phase_messages.get("intraday_1")
    assert result.phase_messages.get("performance")
    assert result.phase_messages.get("cio_review")
    assert "2026-07-09" in result.schedule_log
    assert (tmp_path / "intelligence.json").exists()
    assert (tmp_path / "daily_plan_context.json").exists()
    assert (tmp_path / "cio_inputs.json").exists()
    assert (tmp_path / "performance_report.json").exists()


def test_live_session_default_has_no_positions():
    assert load_positions(None, fixture_mode=False) == []