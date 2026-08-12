"""Phase window resolution and resilient phase execution."""

from __future__ import annotations

import traceback
from datetime import datetime
from typing import Callable, TextIO, TypeVar

from trading_agent.runtime.stdio import safe_write
from trading_agent.session.config import SessionConfig
from trading_agent.session.schedule import DeskPhaseKind, DeskSchedule, resolve_start_phase

T = TypeVar("T")

PHASE_ORDER = [
    DeskPhaseKind.INTELLIGENCE,
    DeskPhaseKind.RESEARCH,
    DeskPhaseKind.CIO_APPROVAL,
    DeskPhaseKind.PREOPEN,
    DeskPhaseKind.INTRADAY,
    DeskPhaseKind.PERFORMANCE,
    DeskPhaseKind.CIO_REVIEW,
    DeskPhaseKind.EVENING_SCAN,
]


def resolve_first_phase(
    config: SessionConfig,
    current: datetime,
    schedule: DeskSchedule,
) -> DeskPhaseKind:
    """Pick the first desk phase to run for this session.

    Late starts (after a phase's scheduled time) jump forward via
    ``resolve_start_phase`` so a night kickstart does not re-blast MI→CIO→…
    to Discord. Prep-only windows that end at preopen still start at
    intelligence when the day has not yet reached open.
    """
    if config.from_phase is not None:
        return config.from_phase
    if config.fixture_mode or config.dry_run or not config.wait_for_schedule:
        return DeskPhaseKind.INTELLIGENCE

    # Full-day or mid/late day: honor clock (skip completed phases).
    # Prep-only (until=preopen) before open: still run intelligence→preopen.
    if config.until_phase == DeskPhaseKind.PREOPEN:
        if current.astimezone(schedule.timezone) < schedule.market_open:
            return DeskPhaseKind.INTELLIGENCE
        # Already past open — no prep replay
        return resolve_start_phase(current, schedule, None)

    return resolve_start_phase(current, schedule, None)


def resolve_phase_window(
    config: SessionConfig,
    current: datetime,
    schedule: DeskSchedule,
) -> tuple[DeskPhaseKind, list[DeskPhaseKind]]:
    """Return (start_kind, ordered phases to execute)."""
    start_kind = resolve_first_phase(config, current, schedule)
    end_kind = config.until_phase if config.until_phase is not None else PHASE_ORDER[-1]

    start_index = PHASE_ORDER.index(start_kind)
    end_index = PHASE_ORDER.index(end_kind)
    if start_index > end_index:
        return start_kind, []
    return start_kind, PHASE_ORDER[start_index : end_index + 1]


def run_phase_safe(
    label: str,
    fn: Callable[[], T],
    *,
    log: TextIO | None,
    critical: bool = True,
) -> T | None:
    """Run a desk phase; log tracebacks and optionally continue."""
    try:
        return fn()
    except Exception as exc:
        safe_write(log, f"[error] {label} failed: {exc}")
        safe_write(log, traceback.format_exc())
        if critical:
            raise
        return None