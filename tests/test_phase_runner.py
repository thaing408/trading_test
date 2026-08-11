"""Tests for desk phase window resolution."""

from __future__ import annotations

from datetime import date, datetime

from trading_agent.session.config import SessionConfig
from trading_agent.session.phase_runner import resolve_first_phase, resolve_phase_window
from trading_agent.session.schedule import PT, DeskPhaseKind, compute_desk_schedule


def test_until_preopen_before_open_starts_intelligence():
    schedule = compute_desk_schedule(date(2026, 7, 9), interval_minutes=15)
    morning = datetime(2026, 7, 9, 5, 30, tzinfo=PT)
    config = SessionConfig(
        until_phase=DeskPhaseKind.PREOPEN,
        wait_for_schedule=True,
    )
    start, phases = resolve_phase_window(config, morning, schedule)
    assert start == DeskPhaseKind.INTELLIGENCE
    assert DeskPhaseKind.PREOPEN in phases


def test_until_preopen_after_open_does_not_replay_prep():
    """Past open: prep-only scope must not re-run MI→preopen."""
    schedule = compute_desk_schedule(date(2026, 7, 9), interval_minutes=15)
    late = datetime(2026, 7, 9, 10, 0, tzinfo=PT)
    config = SessionConfig(
        until_phase=DeskPhaseKind.PREOPEN,
        wait_for_schedule=True,
    )
    start, phases = resolve_phase_window(config, late, schedule)
    # start is past preopen window end → empty phase list
    assert start == DeskPhaseKind.INTRADAY or phases == []
    assert DeskPhaseKind.INTELLIGENCE not in phases


def test_full_day_with_until_cio_review_late_skips_to_intraday():
    """until=cio_review must NOT force Intelligence (night kickstart flood)."""
    schedule = compute_desk_schedule(date(2026, 7, 9), interval_minutes=15)
    late = datetime(2026, 7, 9, 10, 0, tzinfo=PT)
    config = SessionConfig(
        until_phase=DeskPhaseKind.CIO_REVIEW,
        wait_for_schedule=True,
    )
    start = resolve_first_phase(config, late, schedule)
    assert start == DeskPhaseKind.INTRADAY


def test_explicit_from_phase_overrides_late_start():
    schedule = compute_desk_schedule(date(2026, 7, 9), interval_minutes=15)
    late = datetime(2026, 7, 9, 10, 0, tzinfo=PT)
    config = SessionConfig(from_phase=DeskPhaseKind.RESEARCH)
    assert resolve_first_phase(config, late, schedule) == DeskPhaseKind.RESEARCH


def test_full_day_late_start_skips_completed_phases():
    schedule = compute_desk_schedule(date(2026, 7, 9), interval_minutes=15)
    late = datetime(2026, 7, 9, 10, 0, tzinfo=PT)
    config = SessionConfig(wait_for_schedule=True)
    assert resolve_first_phase(config, late, schedule) == DeskPhaseKind.INTRADAY