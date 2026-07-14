"""US equity desk schedule — Pacific Time phases + legacy ET helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
PT = ZoneInfo("America/Los_Angeles")

# Legacy ET schedule
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)
PREMARKET_PUSH = time(8, 0)

# Pacific desk phase times
INTELLIGENCE_TIME = time(2, 0)
RESEARCH_TIME = time(5, 0)
CIO_APPROVAL_TIME = time(6, 0)
PREOPEN_TIME = time(6, 25)
DESK_OPEN_PT = time(6, 30)
DESK_CLOSE_PT = time(13, 0)
PERFORMANCE_TIME = time(13, 15)
CIO_REVIEW_TIME = time(13, 30)

# Light discovery refresh slots (Pacific Time) during RTH — not full CIO rebuilds.
# 07:00 PT = 10:00 ET (post-open range set)
# 09:30 PT = 12:30 ET (midday rotation)
# 11:00 PT = 14:00 ET (afternoon opportunity check before close)
DISCOVERY_REFRESH_TIMES_PT: tuple[time, ...] = (
    time(7, 0),
    time(9, 30),
    time(11, 0),
)


class DeskPhaseKind(str, Enum):
    INTELLIGENCE = "intelligence"
    RESEARCH = "research"
    CIO_APPROVAL = "cio_approval"
    PREOPEN = "preopen"
    INTRADAY = "intraday"
    PERFORMANCE = "performance"
    CIO_REVIEW = "cio_review"


@dataclass(frozen=True)
class DeskPhase:
    kind: DeskPhaseKind
    label: str
    scheduled_at: datetime


@dataclass(frozen=True)
class SessionSchedule:
    trading_date: date
    premarket_push: datetime
    market_open: datetime
    market_close: datetime
    intraday_cycles: tuple[datetime, ...]


@dataclass(frozen=True)
class DeskSchedule:
    trading_date: date
    timezone: ZoneInfo
    phases: tuple[DeskPhase, ...]
    intraday_cycles: tuple[datetime, ...]
    market_open: datetime
    market_close: datetime
    discovery_refreshes: tuple[datetime, ...] = ()


def resolve_trading_date(
    explicit: date | None = None,
    now: datetime | None = None,
    tz: ZoneInfo = PT,
) -> date:
    """Next US session date using the given timezone for open/close boundaries."""
    if explicit:
        return explicit
    current = now or datetime.now(tz)
    if current.tzinfo is None:
        current = current.replace(tzinfo=tz)
    else:
        current = current.astimezone(tz)

    candidate = current.date()
    close_boundary = datetime.combine(candidate, DESK_CLOSE_PT, tzinfo=tz)
    if candidate.weekday() < 5 and current < close_boundary:
        return candidate
    return _next_weekday(candidate)


def _next_weekday(start: date) -> date:
    day = start + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def compute_desk_schedule(
    trading_date: date,
    interval_minutes: int = 15,
    tz: ZoneInfo = PT,
) -> DeskSchedule:
    """Compute all 7 desk phases and intraday cycles for a trading day (Pacific Time)."""
    intelligence = datetime.combine(trading_date, INTELLIGENCE_TIME, tzinfo=tz)
    research = datetime.combine(trading_date, RESEARCH_TIME, tzinfo=tz)
    cio_approval = datetime.combine(trading_date, CIO_APPROVAL_TIME, tzinfo=tz)
    preopen = datetime.combine(trading_date, PREOPEN_TIME, tzinfo=tz)
    open_dt = datetime.combine(trading_date, DESK_OPEN_PT, tzinfo=tz)
    close_dt = datetime.combine(trading_date, DESK_CLOSE_PT, tzinfo=tz)
    performance = datetime.combine(trading_date, PERFORMANCE_TIME, tzinfo=tz)
    cio_review = datetime.combine(trading_date, CIO_REVIEW_TIME, tzinfo=tz)

    cycles: list[datetime] = []
    cursor = open_dt
    while cursor < close_dt:
        cycles.append(cursor)
        cursor += timedelta(minutes=interval_minutes)

    discovery: list[datetime] = []
    for t in DISCOVERY_REFRESH_TIMES_PT:
        dt = datetime.combine(trading_date, t, tzinfo=tz)
        if open_dt < dt < close_dt:
            discovery.append(dt)

    phases = (
        DeskPhase(DeskPhaseKind.INTELLIGENCE, "Market Intelligence Team", intelligence),
        DeskPhase(DeskPhaseKind.RESEARCH, "Trading Research Team", research),
        DeskPhase(DeskPhaseKind.CIO_APPROVAL, "Chief Investment Officer (Final Approval)", cio_approval),
        DeskPhase(DeskPhaseKind.PREOPEN, "Trading Desk (Pre-Open Check)", preopen),
        DeskPhase(DeskPhaseKind.INTRADAY, "Trading Desk", open_dt),
        DeskPhase(DeskPhaseKind.PERFORMANCE, "Performance & Learning Team", performance),
        DeskPhase(DeskPhaseKind.CIO_REVIEW, "Chief Investment Officer Daily Review", cio_review),
    )

    return DeskSchedule(
        trading_date=trading_date,
        timezone=tz,
        phases=phases,
        intraday_cycles=tuple(cycles),
        market_open=open_dt,
        market_close=close_dt,
        discovery_refreshes=tuple(discovery),
    )


def resolve_start_phase(
    now: datetime,
    schedule: DeskSchedule,
    explicit: DeskPhaseKind | None = None,
) -> DeskPhaseKind:
    """Return the first phase to execute (skip completed phases on late start)."""
    if explicit:
        return explicit
    if now.tzinfo is None:
        now = now.replace(tzinfo=schedule.timezone)
    else:
        now = now.astimezone(schedule.timezone)

    ordered = [
        DeskPhaseKind.INTELLIGENCE,
        DeskPhaseKind.RESEARCH,
        DeskPhaseKind.CIO_APPROVAL,
        DeskPhaseKind.PREOPEN,
        DeskPhaseKind.INTRADAY,
        DeskPhaseKind.PERFORMANCE,
        DeskPhaseKind.CIO_REVIEW,
    ]
    phase_times = {
        DeskPhaseKind.INTELLIGENCE: schedule.phases[0].scheduled_at,
        DeskPhaseKind.RESEARCH: schedule.phases[1].scheduled_at,
        DeskPhaseKind.CIO_APPROVAL: schedule.phases[2].scheduled_at,
        DeskPhaseKind.PREOPEN: schedule.phases[3].scheduled_at,
        DeskPhaseKind.INTRADAY: schedule.market_open,
        DeskPhaseKind.PERFORMANCE: schedule.phases[5].scheduled_at,
        DeskPhaseKind.CIO_REVIEW: schedule.phases[6].scheduled_at,
    }
    for kind in reversed(ordered):
        if now >= phase_times[kind]:
            return kind
    return DeskPhaseKind.INTELLIGENCE


def render_desk_schedule_log(schedule: DeskSchedule, interval_minutes: int) -> str:
    lines = [
        f"# Desk Schedule — {schedule.trading_date.isoformat()} (America/Los_Angeles)",
        f"- Market Intelligence: {schedule.phases[0].scheduled_at.strftime('%H:%M %Z')}",
        f"- Trading Research: {schedule.phases[1].scheduled_at.strftime('%H:%M %Z')}",
        f"- CIO Final Approval: {schedule.phases[2].scheduled_at.strftime('%H:%M %Z')}",
        f"- Pre-Open Check: {schedule.phases[3].scheduled_at.strftime('%H:%M %Z')}",
        f"- Trading Desk open: {schedule.market_open.strftime('%H:%M %Z')} "
        f"({schedule.market_open.astimezone(ET).strftime('%H:%M %Z')} ET)",
        f"- Trading Desk close: {schedule.market_close.strftime('%H:%M %Z')} "
        f"({schedule.market_close.astimezone(ET).strftime('%H:%M %Z')} ET)",
        f"- Performance Review: {schedule.phases[5].scheduled_at.strftime('%H:%M %Z')}",
        f"- CIO Daily Review: {schedule.phases[6].scheduled_at.strftime('%H:%M %Z')}",
        f"- Intraday interval: {interval_minutes} minutes (baseline when flat)",
        f"- In-position PT/SL interval: {DEFAULT_IN_POSITION_INTERVAL_MINUTES} minutes "
        f"(while open positions exist; adaptive)",
        f"- Intraday cycle count (baseline grid): {len(schedule.intraday_cycles)}",
        f"- Discovery refresh slots (PT): {len(schedule.discovery_refreshes)} "
        f"(light rescreen — not full CIO rebuild)",
        "",
        "## Discovery refresh times (PT)",
    ]
    for index, slot in enumerate(schedule.discovery_refreshes, start=1):
        lines.append(
            f"{index}. {slot.strftime('%H:%M %Z')} "
            f"({slot.astimezone(ET).strftime('%H:%M %Z')} ET)"
        )
    lines.extend(
        [
            "",
            "## Intraday cycle times (PT, baseline grid)",
        ]
    )
    for index, cycle in enumerate(schedule.intraday_cycles, start=1):
        lines.append(f"{index}. {cycle.strftime('%H:%M %Z')}")
    return "\n".join(lines) + "\n"


def compute_session_schedule(
    trading_date: date,
    interval_minutes: int = 15,
) -> SessionSchedule:
    """Legacy ET schedule for backward compatibility."""
    premarket = datetime.combine(trading_date, PREMARKET_PUSH, tzinfo=ET)
    open_dt = datetime.combine(trading_date, MARKET_OPEN, tzinfo=ET)
    close_dt = datetime.combine(trading_date, MARKET_CLOSE, tzinfo=ET)

    cycles: list[datetime] = []
    cursor = open_dt
    while cursor < close_dt:
        cycles.append(cursor)
        cursor += timedelta(minutes=interval_minutes)

    return SessionSchedule(
        trading_date=trading_date,
        premarket_push=premarket,
        market_open=open_dt,
        market_close=close_dt,
        intraday_cycles=tuple(cycles),
    )


def render_schedule_log(schedule: SessionSchedule, interval_minutes: int) -> str:
    lines = [
        f"# Session Schedule — {schedule.trading_date.isoformat()} (America/New_York)",
        f"- Pre-market scout push: {schedule.premarket_push.strftime('%Y-%m-%d %H:%M %Z')}",
        f"- Regular session open: {schedule.market_open.strftime('%Y-%m-%d %H:%M %Z')}",
        f"- Regular session close: {schedule.market_close.strftime('%Y-%m-%d %H:%M %Z')}",
        f"- Intraday interval: {interval_minutes} minutes",
        f"- Intraday cycle count: {len(schedule.intraday_cycles)}",
        "",
        "## Intraday cycle times",
    ]
    for index, cycle in enumerate(schedule.intraday_cycles, start=1):
        lines.append(f"{index}. {cycle.strftime('%H:%M %Z')}")
    return "\n".join(lines) + "\n"


# Defaults for adaptive PT/SL monitoring cadence (minutes)
DEFAULT_INTRADAY_INTERVAL_MINUTES = 15
DEFAULT_IN_POSITION_INTERVAL_MINUTES = 3


def next_intraday_interval_minutes(
    baseline_minutes: int,
    has_open_positions: bool,
    *,
    in_position_minutes: int | None = None,
) -> int:
    """Return minutes to wait until the next PT/SL (intraday) check.

    Flat book → baseline (desk default, e.g. 15).
    Open position(s) → shorter interval (e.g. 3) until flat again.
    Always ≥ 1 minute to avoid busy-looping.
    """
    baseline = max(1, int(baseline_minutes))
    if in_position_minutes is None:
        fast = DEFAULT_IN_POSITION_INTERVAL_MINUTES
    else:
        fast = max(1, int(in_position_minutes))
    if not has_open_positions:
        return baseline
    # Strictly shorter than baseline when possible
    if fast >= baseline:
        fast = max(1, baseline - 1) if baseline > 1 else 1
    return fast


def seconds_until(target: datetime, now: datetime) -> float:
    tz = target.tzinfo or PT
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)
    if target.tzinfo is None:
        target = target.replace(tzinfo=tz)
    else:
        target = target.astimezone(tz)
    return max(0.0, (target - now).total_seconds())


def is_regular_session(now: datetime, schedule: DeskSchedule | SessionSchedule) -> bool:
    tz = schedule.market_open.tzinfo or PT
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)
    return schedule.market_open <= now < schedule.market_close