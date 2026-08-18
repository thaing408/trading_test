"""Wrap phase status + desk schedule for snapshot assembly."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from trading_agent.desk_ui.phase import PhaseStatus, current_phase_status
from trading_agent.session.schedule import (
    DESK_CLOSE_PT,
    DeskSchedule,
    PT,
    compute_desk_schedule,
    resolve_trading_date,
)


def resolve_ui_trading_date(
    now: datetime | None = None,
    *,
    tz: ZoneInfo = PT,
) -> date:
    """Trading date for desk UI / desk-status (investigation surface).

    Orchestrator ``resolve_trading_date`` rolls to the *next* session after
    DESK_CLOSE_PT (13:00 PT). Operators reviewing overnight still care about
    the session that just finished (today's book/plan), so on a weekday after
    close we keep the calendar date until midnight PT.

    Explicit ``--date`` still overrides via callers that pass trading_date.
    """
    current = now or datetime.now(tz)
    if current.tzinfo is None:
        current = current.replace(tzinfo=tz)
    else:
        current = current.astimezone(tz)

    orchestrator = resolve_trading_date(now=current, tz=tz)
    cal = current.date()
    if cal.weekday() < 5:
        close = datetime.combine(cal, DESK_CLOSE_PT, tzinfo=tz)
        if current >= close and cal != orchestrator:
            return cal
    return orchestrator


def resolve_phase(
    now: datetime | None = None,
    *,
    trading_date: date | None = None,
) -> tuple[date, DeskSchedule, PhaseStatus]:
    current = now or datetime.now(PT)
    if current.tzinfo is None:
        current = current.replace(tzinfo=PT)
    else:
        current = current.astimezone(PT)
    td = trading_date or resolve_ui_trading_date(now=current)
    schedule = compute_desk_schedule(td)
    phase = current_phase_status(current, trading_date=td, schedule=schedule)
    return td, schedule, phase
