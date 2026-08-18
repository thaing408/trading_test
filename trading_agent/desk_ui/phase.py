"""Continuous desk phase status for UI/CLI (not orchestrator late-start)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from trading_agent.session.schedule import (
    DESK_CLOSE_PT,
    DESK_OPEN_PT,
    PT,
    DeskSchedule,
    compute_desk_schedule,
)

_WEEKEND_LABEL = "Weekend / next session"
_PRE_SESSION_LABEL = "Pre-session"
_POST_EVENING_LABEL = "Post evening scan"


@dataclass(frozen=True)
class PhaseStatus:
    trading_date: date
    phase_kind: str
    phase_label: str
    phase_started_at: datetime | None
    next_phase_kind: str | None
    next_phase_at: datetime | None
    next_discovery_at: datetime | None
    in_intraday_window: bool
    discovery_slot_label: str | None


def current_phase_status(
    now: datetime | None = None,
    *,
    trading_date: date | None = None,
    schedule: DeskSchedule | None = None,
    tz: ZoneInfo = PT,
) -> PhaseStatus:
    """Resolve continuous phase chip state for a point in time (PT)."""
    current = now or datetime.now(tz)
    if current.tzinfo is None:
        current = current.replace(tzinfo=tz)
    else:
        current = current.astimezone(tz)

    if trading_date is not None:
        td = trading_date
    else:
        # Late import avoids circular import with schedule_status → phase
        from trading_agent.desk_ui.readers.schedule_status import resolve_ui_trading_date

        td = resolve_ui_trading_date(now=current, tz=tz)
    sched = schedule or compute_desk_schedule(td, tz=tz)

    open_dt = datetime.combine(td, DESK_OPEN_PT, tzinfo=tz)
    close_dt = datetime.combine(td, DESK_CLOSE_PT, tzinfo=tz)
    in_window = open_dt <= current < close_dt

    # Weekend relative to resolved trading date: if calendar day is Sat/Sun and
    # we're not yet on that trading_date's first phase, still show weekend when
    # current calendar weekday is weekend AND before first phase of next session.
    phases = list(sched.phases)
    if not phases:
        return PhaseStatus(
            trading_date=td,
            phase_kind="weekend",
            phase_label=_WEEKEND_LABEL,
            phase_started_at=None,
            next_phase_kind=None,
            next_phase_at=None,
            next_discovery_at=_next_discovery(sched, current),
            in_intraday_window=False,
            discovery_slot_label=_discovery_slot_label(sched, current),
        )

    first = phases[0]
    last = phases[-1]

    if current.date().weekday() >= 5 and current < first.scheduled_at:
        return PhaseStatus(
            trading_date=td,
            phase_kind="weekend",
            phase_label=_WEEKEND_LABEL,
            phase_started_at=None,
            next_phase_kind=first.kind.value,
            next_phase_at=first.scheduled_at,
            next_discovery_at=_next_discovery(sched, current),
            in_intraday_window=False,
            discovery_slot_label=_discovery_slot_label(sched, current),
        )

    if current < first.scheduled_at:
        return PhaseStatus(
            trading_date=td,
            phase_kind="pre_session",
            phase_label=_PRE_SESSION_LABEL,
            phase_started_at=None,
            next_phase_kind=first.kind.value,
            next_phase_at=first.scheduled_at,
            next_discovery_at=_next_discovery(sched, current),
            in_intraday_window=in_window,
            discovery_slot_label=_discovery_slot_label(sched, current),
        )

    active_idx = 0
    for i, phase in enumerate(phases):
        if phase.scheduled_at <= current:
            active_idx = i
        else:
            break

    active = phases[active_idx]
    if active_idx + 1 < len(phases):
        nxt = phases[active_idx + 1]
        next_kind: str | None = nxt.kind.value
        next_at: datetime | None = nxt.scheduled_at
        phase_kind = active.kind.value
        phase_label = active.label
        started = active.scheduled_at
    else:
        # After last phase (evening_scan)
        if current >= last.scheduled_at:
            phase_kind = "post_evening"
            phase_label = _POST_EVENING_LABEL
            started = last.scheduled_at
            next_kind = None
            next_at = None
        else:
            phase_kind = active.kind.value
            phase_label = active.label
            started = active.scheduled_at
            next_kind = None
            next_at = None

    # Between desk close and performance: still active named phase (intraday)
    # with in_intraday_window=False — label can note desk closed.
    if (
        phase_kind == "intraday"
        and current >= close_dt
        and next_kind == "performance"
    ):
        phase_label = f"{active.label} (desk closed — awaiting performance)"

    return PhaseStatus(
        trading_date=td,
        phase_kind=phase_kind,
        phase_label=phase_label,
        phase_started_at=started,
        next_phase_kind=next_kind,
        next_phase_at=next_at,
        next_discovery_at=_next_discovery(sched, current),
        in_intraday_window=in_window,
        discovery_slot_label=_discovery_slot_label(sched, current),
    )


def _next_discovery(schedule: DeskSchedule, now: datetime) -> datetime | None:
    for dt in schedule.discovery_refreshes or ():
        if dt > now:
            return dt
    return None


def _discovery_slot_label(schedule: DeskSchedule, now: datetime) -> str | None:
    window = timedelta(minutes=5)
    for dt in schedule.discovery_refreshes or ():
        if abs(now - dt) <= window:
            return dt.strftime("%H:%M PT")
    return None
