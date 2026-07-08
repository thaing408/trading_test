"""Orchestrate pre-market scout, CIO summary, and intraday Discord pushes."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, TextIO
from zoneinfo import ZoneInfo

from trading_agent.cio.config import CIOConfig
from trading_agent.cio.pipeline import run_cio_pipeline
from trading_agent.config import AgentConfig
from trading_agent.discord.config import DiscordConfig
from trading_agent.discord.poster import DiscordPostError, post_message
from trading_agent.intraday.config import IntradayConfig
from trading_agent.intraday.pipeline import run_intraday_pipeline
from trading_agent.pipeline import run_pipeline
from trading_agent.session.config import SessionConfig
from trading_agent.session.context import default_session_dir, plan_to_context, save_plan_context
from trading_agent.session.play_formatter import (
    format_cio_plays,
    format_intraday_plays,
    format_premarket_plays,
)
from trading_agent.session.schedule import (
    ET,
    compute_session_schedule,
    is_regular_session,
    render_schedule_log,
    resolve_trading_date,
    seconds_until,
)

SleepFn = Callable[[float], None]


@dataclass
class SessionResult:
    trading_date: str
    schedule_log: str
    premarket_message: str
    cio_message: str = ""
    intraday_messages: list[str] = field(default_factory=list)
    plan_context_path: str = ""
    discord_posts: list[dict] = field(default_factory=list)


def _log(handle: TextIO | None, message: str) -> None:
    print(message)
    if handle:
        handle.write(message + "\n")
        handle.flush()


def _deliver(
    content: str,
    title: str,
    *,
    config: SessionConfig,
    discord: DiscordConfig,
    log: TextIO | None,
    posts: list[dict],
) -> None:
    _log(log, "")
    _log(log, f"=== {title} ===")
    _log(log, content)
    if config.dry_run or config.no_discord:
        _log(log, f"[dry-run] Discord post skipped for: {title}")
        return
    try:
        results = post_message(content, discord, username="Trading Agent")
        posts.extend(results)
        _log(log, f"[discord] Posted {title} ({len(results)} chunk(s))")
    except DiscordPostError as exc:
        _log(log, f"[discord] Skipped {title}: {exc}")


def run_session(
    config: SessionConfig,
    *,
    now: datetime | None = None,
    sleep_fn: SleepFn | None = None,
    log: TextIO | None = None,
) -> SessionResult:
    """Run a full trading session: pre-market scout then intraday cycles."""
    sleep = sleep_fn or time.sleep
    current = now or datetime.now(ET)
    if current.tzinfo is None:
        current = current.replace(tzinfo=ET)
    else:
        current = current.astimezone(ET)

    trading_date = resolve_trading_date(config.trading_date, current)
    schedule = compute_session_schedule(trading_date, config.intraday_interval_minutes)
    schedule_log = render_schedule_log(schedule, config.intraday_interval_minutes)

    session_dir = config.session_dir or default_session_dir(trading_date)
    discord = DiscordConfig.from_env()
    posts: list[dict] = []

    wait = config.wait_for_schedule and not config.fixture_mode and not config.dry_run
    if wait and seconds_until(schedule.premarket_push, current) > 0:
        delay = seconds_until(schedule.premarket_push, current)
        _log(log, f"Waiting {delay:.0f}s until pre-market scout at {schedule.premarket_push:%H:%M %Z}")
        sleep(delay)
        current = datetime.now(ET)

    agent_config = AgentConfig.from_env()
    agent_config.fixture_mode = config.fixture_mode
    agent_config.use_live_data = not config.fixture_mode

    _log(log, schedule_log)
    plan = run_pipeline(agent_config)
    context = plan_to_context(plan)
    plan_path = save_plan_context(context, session_dir)
    premarket_message = format_premarket_plays(plan)
    _deliver(
        premarket_message,
        "Pre-Market Scout",
        config=config,
        discord=discord,
        log=log,
        posts=posts,
    )

    cio_message = ""
    watch_symbols = list(context.get("top_watchlist", []))
    if config.include_cio:
        cio_config = CIOConfig.from_env()
        cio_config.fixture_mode = config.fixture_mode
        cio_config.portfolio_value = config.portfolio_value
        cio_report = run_cio_pipeline(cio_config)
        cio_message = format_cio_plays(cio_report)
        for trade in cio_report.approved:
            if trade.ticker not in watch_symbols:
                watch_symbols.append(trade.ticker)
        _deliver(
            cio_message,
            "CIO Summary",
            config=config,
            discord=discord,
            log=log,
            posts=posts,
        )

    intraday_messages: list[str] = []
    cycles_to_run = config.intraday_cycles
    if not config.fixture_mode and not config.dry_run:
        cycles_to_run = len(schedule.intraday_cycles)

    for cycle_index in range(1, cycles_to_run + 1):
        if wait:
            if cycle_index <= len(schedule.intraday_cycles):
                target = schedule.intraday_cycles[cycle_index - 1]
                delay = seconds_until(target, datetime.now(ET))
                if delay > 0:
                    _log(log, f"Waiting {delay:.0f}s until intraday cycle {cycle_index} at {target:%H:%M %Z}")
                    sleep(delay)
            elif not is_regular_session(datetime.now(ET), schedule):
                _log(log, "Regular session closed — stopping intraday cycles.")
                break

        intraday_config = IntradayConfig.from_env()
        intraday_config.fixture_mode = config.fixture_mode
        intraday_config.use_live_data = not config.fixture_mode
        intraday_config.plan_file = str(plan_path)
        # Live default: no --positions => empty book, watchlist scouting only.
        intraday_config.positions_file = config.positions_file if config.positions_file else None
        intraday_config.session_file = config.session_file
        intraday_config.cycles = cycle_index
        intraday_config.watch_symbols = watch_symbols

        report = run_intraday_pipeline(intraday_config)
        message = format_intraday_plays(report, cycle_index)
        intraday_messages.append(message)
        _deliver(
            message,
            f"Intraday Cycle {cycle_index}",
            config=config,
            discord=discord,
            log=log,
            posts=posts,
        )

    return SessionResult(
        trading_date=trading_date.isoformat(),
        schedule_log=schedule_log,
        premarket_message=premarket_message,
        cio_message=cio_message,
        intraday_messages=intraday_messages,
        plan_context_path=str(plan_path),
        discord_posts=posts,
    )


def run_session_cli(config: SessionConfig) -> int:
    log_path = config.log_file
    handle: TextIO | None = None
    if log_path:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        handle = open(log_path, "w", encoding="utf-8")
    try:
        run_session(config, log=handle or sys.stdout)
        return 0
    finally:
        if handle:
            handle.close()