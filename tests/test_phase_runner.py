"""Tests for desk phase window resolution."""

from __future__ import annotations

from datetime import date, datetime

from trading_agent.session.config import SessionConfig
from trading_agent.session.phase_runner import resolve_first_phase, resolve_phase_window
from trading_agent.session.schedule import PT, DeskPhaseKind, compute_desk_schedule


def test_until_preopen_always_starts_intelligence_when_late():
    schedule = compute_desk_schedule(date(2026, 7, 9), interval_minutes=15)
    late = datetime(2026, 7, 9, 10, 0, tzinfo=PT)
    config = SessionConfig(
        until_phase=DeskPhaseKind.PREOPEN,
        wait_for_schedule=True,
    )
    start, phases = resolve_phase_window(config, late, schedule)
    assert start == DeskPhaseKind.INTELLIGENCE
    assert phases == [
        DeskPhaseKind.INTELLIGENCE,
        DeskPhaseKind.RESEARCH,
        DeskPhaseKind.CIO_APPROVAL,
        DeskPhaseKind.PREOPEN,
    ]


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