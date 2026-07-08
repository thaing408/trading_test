"""US equity session schedule in America/New_York."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)
PREMARKET_PUSH = time(8, 0)


@dataclass(frozen=True)
class SessionSchedule:
    trading_date: date
    premarket_push: datetime
    market_open: datetime
    market_close: datetime
    intraday_cycles: tuple[datetime, ...]


def resolve_trading_date(
    explicit: date | None = None,
    now: datetime | None = None,
) -> date:
    """Next US session date: explicit override, else today if weekday pre-close, else next weekday."""
    if explicit:
        return explicit
    current = now or datetime.now(ET)
    if current.tzinfo is None:
        current = current.replace(tzinfo=ET)
    else:
        current = current.astimezone(ET)

    candidate = current.date()
    if candidate.weekday() < 5 and current.time() < MARKET_CLOSE:
        return candidate
    return _next_weekday(candidate)


def _next_weekday(start: date) -> date:
    day = start + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def compute_session_schedule(
    trading_date: date,
    interval_minutes: int = 15,
) -> SessionSchedule:
    """Compute pre-market push and intraday cycle timestamps for a trading day."""
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


def seconds_until(target: datetime, now: datetime) -> float:
    if now.tzinfo is None:
        now = now.replace(tzinfo=ET)
    else:
        now = now.astimezone(ET)
    if target.tzinfo is None:
        target = target.replace(tzinfo=ET)
    else:
        target = target.astimezone(ET)
    return max(0.0, (target - now).total_seconds())


def is_regular_session(now: datetime, schedule: SessionSchedule) -> bool:
    if now.tzinfo is None:
        now = now.replace(tzinfo=ET)
    else:
        now = now.astimezone(ET)
    return schedule.market_open <= now < schedule.market_close