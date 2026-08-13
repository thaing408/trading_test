"""Tests for full session orchestrator fixture output."""

from __future__ import annotations

from datetime import date

from trading_agent.intraday.plan_loader import load_positions
from trading_agent.session.config import SessionConfig
from trading_agent.session.orchestrator import run_session


def test_fixture_session_methods_lab_no_cio_desk(tmp_path):
    """trading_test default: methods research, CIO phases skipped (stub messages only)."""
    config = SessionConfig(
        fixture_mode=True,
        dry_run=True,
        trading_date=date(2026, 7, 9),
        intraday_cycles=1,
        wait_for_schedule=False,
        session_dir=tmp_path,
        product_mode="methods",
        include_cio=False,
    )
    result = run_session(config)

    assert result.phase_messages.get("intelligence")
    assert result.phase_messages.get("research")
    assert result.phase_messages.get("methods_research")
    assert "no CIO" in (result.phase_messages.get("research") or "").lower() or "methods" in (
        result.phase_messages.get("research") or ""
    ).lower()
    # CIO phases present as skip stubs, not full capital decisions
    assert "skipped" in (result.phase_messages.get("cio_approval") or "").lower()
    assert "skipped" in (result.phase_messages.get("cio_review") or "").lower()
    assert result.phase_messages.get("preopen")
    assert result.phase_messages.get("intraday_1")
    assert result.phase_messages.get("performance")
    assert result.phase_messages.get("evening_scan")
    assert "2026-07-09" in result.schedule_log
    assert (tmp_path / "intelligence.json").exists()
    assert (tmp_path / "daily_plan_context.json").exists()
    # No CIO snapshot in methods lab
    assert not (tmp_path / "cio_inputs.json").exists()
    assert (tmp_path / "performance_report.json").exists()


def test_desk_mode_still_runs_cio_when_enabled(tmp_path):
    """Optional desk mode (include_cio) still produces CIO snapshot."""
    config = SessionConfig(
        fixture_mode=True,
        dry_run=True,
        trading_date=date(2026, 7, 9),
        intraday_cycles=1,
        wait_for_schedule=False,
        session_dir=tmp_path,
        product_mode="desk",
        include_cio=True,
    )
    result = run_session(config)
    assert result.phase_messages.get("cio_approval")
    assert "skipped" not in (result.phase_messages.get("cio_approval") or "").lower()
    assert (tmp_path / "cio_inputs.json").exists()


def test_live_session_default_has_no_positions():
    assert load_positions(None, fixture_mode=False) == []


def test_until_preopen_methods_lab(tmp_path):
    from trading_agent.session.schedule import DeskPhaseKind

    config = SessionConfig(
        fixture_mode=True,
        dry_run=True,
        trading_date=date(2026, 7, 9),
        until_phase=DeskPhaseKind.PREOPEN,
        wait_for_schedule=False,
        session_dir=tmp_path,
        product_mode="methods",
        include_cio=False,
    )
    result = run_session(config)
    assert result.phase_messages.get("intelligence")
    assert result.phase_messages.get("research")
    assert result.phase_messages.get("preopen")
    assert "intraday_1" not in result.phase_messages
    assert "performance" not in result.phase_messages


def test_product_defaults_methods_lab():
    from trading_agent.product import PRODUCT_ID, is_methods_lab, product_mode

    assert PRODUCT_ID == "trading_test"
    assert product_mode() == "methods"
    assert is_methods_lab() is True
    cfg = SessionConfig.from_env()
    assert cfg.product_mode == "methods"
    assert cfg.include_cio is False
