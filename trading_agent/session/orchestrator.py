"""Orchestrate the full Pacific-time trading desk day."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, TextIO
from zoneinfo import ZoneInfo

from trading_agent.cio.config import CIOConfig
from trading_agent.session.cio_snapshot import save_cio_approval_snapshot
from trading_agent.cio.pipeline import run_cio_pipeline
from trading_agent.config import AgentConfig
from trading_agent.discord.config import DiscordConfig
from trading_agent.discord.poster import DiscordPostError, post_message
from trading_agent.intraday.config import IntradayConfig
from trading_agent.intraday.pipeline import run_intraday_pipeline
from trading_agent.performance.config import PerformanceConfig
from trading_agent.performance.pipeline import run_performance_pipeline
from trading_agent.pipeline import run_pipeline
from trading_agent.session.config import SessionConfig
from trading_agent.session.context import (
    default_session_dir,
    load_saved_plan_context,
    plan_to_context,
    save_intelligence,
    save_intraday_flags,
    save_performance_report,
    save_plan_context,
)
from trading_agent.session.intelligence import run_intelligence_pass
from trading_agent.session.play_formatter import (
    format_cio_plays,
    format_cio_review,
    format_intelligence_brief,
    format_intraday_plays,
    format_performance_plays,
    format_preopen_check,
    format_research_plays,
)
from trading_agent.session.schedule import (
    PT,
    DeskPhaseKind,
    compute_desk_schedule,
    is_regular_session,
    render_desk_schedule_log,
    resolve_start_phase,
    resolve_trading_date,
    seconds_until,
)

SleepFn = Callable[[float], None]


@dataclass
class SessionResult:
    trading_date: str
    schedule_log: str
    phase_messages: dict[str, str] = field(default_factory=dict)
    plan_context_path: str = ""
    discord_posts: list[dict] = field(default_factory=list)

    @property
    def premarket_message(self) -> str:
        return self.phase_messages.get("research", "")

    @property
    def cio_message(self) -> str:
        return self.phase_messages.get("cio_approval", "")

    @property
    def intraday_messages(self) -> list[str]:
        return [v for k, v in self.phase_messages.items() if k.startswith("intraday_")]


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


def _wait_until(target: datetime, *, wait: bool, sleep: SleepFn, log: TextIO | None, label: str) -> None:
    if not wait:
        return
    delay = seconds_until(target, datetime.now(target.tzinfo or PT))
    if delay > 0:
        _log(log, f"Waiting {delay:.0f}s until {label} at {target:%H:%M %Z}")
        sleep(delay)


def run_session(
    config: SessionConfig,
    *,
    now: datetime | None = None,
    sleep_fn: SleepFn | None = None,
    log: TextIO | None = None,
) -> SessionResult:
    """Run the full PST desk day across all seven team checkpoints."""
    sleep = sleep_fn or time.sleep
    tz = ZoneInfo(config.timezone)
    current = now or datetime.now(tz)
    if current.tzinfo is None:
        current = current.replace(tzinfo=tz)
    else:
        current = current.astimezone(tz)

    trading_date = resolve_trading_date(config.trading_date, current, tz=tz)
    schedule = compute_desk_schedule(trading_date, config.intraday_interval_minutes, tz=tz)
    schedule_log = render_desk_schedule_log(schedule, config.intraday_interval_minutes)
    session_dir = config.session_dir or default_session_dir(trading_date)
    discord = DiscordConfig.from_env()
    posts: list[dict] = []
    phase_messages: dict[str, str] = {}
    wait = config.wait_for_schedule and not config.fixture_mode and not config.dry_run

    start_kind = resolve_start_phase(current, schedule, config.from_phase)
    phase_order = [
        DeskPhaseKind.INTELLIGENCE,
        DeskPhaseKind.RESEARCH,
        DeskPhaseKind.CIO_APPROVAL,
        DeskPhaseKind.PREOPEN,
        DeskPhaseKind.INTRADAY,
        DeskPhaseKind.PERFORMANCE,
        DeskPhaseKind.CIO_REVIEW,
    ]
    start_index = phase_order.index(start_kind)

    _log(log, schedule_log)

    agent_config = AgentConfig.from_env()
    agent_config.fixture_mode = config.fixture_mode
    agent_config.use_live_data = not config.fixture_mode

    plan_path: Path | None = None
    plan_context: dict = {}
    watch_symbols: list[str] = []
    intraday_flags: dict[str, str] = {}

    for phase_kind in phase_order[start_index:]:
        if phase_kind == DeskPhaseKind.INTELLIGENCE:
            phase = schedule.phases[0]
            _wait_until(phase.scheduled_at, wait=wait, sleep=sleep, log=log, label=phase.label)
            brief = run_intelligence_pass(agent_config)
            save_intelligence(brief, session_dir)
            message = format_intelligence_brief(brief)
            phase_messages["intelligence"] = message
            _deliver(message, phase.label, config=config, discord=discord, log=log, posts=posts)

        elif phase_kind == DeskPhaseKind.RESEARCH:
            phase = schedule.phases[1]
            _wait_until(phase.scheduled_at, wait=wait, sleep=sleep, log=log, label=phase.label)
            plan = run_pipeline(agent_config)
            plan_context = plan_to_context(plan)
            plan_path = save_plan_context(plan_context, session_dir)
            save_cio_approval_snapshot(session_dir, plan, config.fixture_mode)
            watch_symbols = list(plan_context.get("top_watchlist", []))
            message = format_research_plays(plan)
            phase_messages["research"] = message
            _deliver(message, phase.label, config=config, discord=discord, log=log, posts=posts)

        elif phase_kind == DeskPhaseKind.CIO_APPROVAL:
            if not config.include_cio:
                continue
            phase = schedule.phases[2]
            _wait_until(phase.scheduled_at, wait=wait, sleep=sleep, log=log, label=phase.label)
            cio_config = CIOConfig.from_env()
            cio_config.fixture_mode = config.fixture_mode
            cio_config.portfolio_value = config.portfolio_value
            cio_config.session_dir = str(session_dir)
            cio_config.cio_mode = "approval"
            cio_report = run_cio_pipeline(cio_config)
            for trade in cio_report.approved:
                if trade.ticker not in watch_symbols:
                    watch_symbols.append(trade.ticker)
            message = format_cio_plays(cio_report, title="CIO Final Approval")
            phase_messages["cio_approval"] = message
            _deliver(message, phase.label, config=config, discord=discord, log=log, posts=posts)

        elif phase_kind == DeskPhaseKind.PREOPEN:
            phase = schedule.phases[3]
            _wait_until(phase.scheduled_at, wait=wait, sleep=sleep, log=log, label=phase.label)
            if plan_path is None:
                plan_path = session_dir / "daily_plan_context.json"
            plan_context = load_saved_plan_context(plan_path)
            intraday_config = IntradayConfig.from_env()
            intraday_config.fixture_mode = config.fixture_mode
            intraday_config.use_live_data = not config.fixture_mode
            intraday_config.plan_file = str(plan_path)
            intraday_config.positions_file = config.positions_file if config.positions_file else None
            intraday_config.session_file = config.session_file
            intraday_config.watch_symbols = watch_symbols
            preopen_report = run_intraday_pipeline(intraday_config)
            message = format_preopen_check(plan_context, preopen_report)
            phase_messages["preopen"] = message
            _deliver(message, phase.label, config=config, discord=discord, log=log, posts=posts)

        elif phase_kind == DeskPhaseKind.INTRADAY:
            cycles_to_run = config.intraday_cycles
            if not config.fixture_mode and not config.dry_run:
                cycles_to_run = len(schedule.intraday_cycles)
            if plan_path is None:
                plan_path = session_dir / "daily_plan_context.json"
            for cycle_index in range(1, cycles_to_run + 1):
                if wait:
                    if cycle_index <= len(schedule.intraday_cycles):
                        target = schedule.intraday_cycles[cycle_index - 1]
                        _wait_until(
                            target,
                            wait=True,
                            sleep=sleep,
                            log=log,
                            label=f"Trading Desk cycle {cycle_index}",
                        )
                    elif not is_regular_session(datetime.now(tz), schedule):
                        _log(log, "Regular session closed — stopping intraday cycles.")
                        break

                intraday_config = IntradayConfig.from_env()
                intraday_config.fixture_mode = config.fixture_mode
                intraday_config.use_live_data = not config.fixture_mode
                intraday_config.plan_file = str(plan_path)
                intraday_config.positions_file = config.positions_file if config.positions_file else None
                intraday_config.session_file = config.session_file
                intraday_config.cycles = cycle_index
                intraday_config.watch_symbols = watch_symbols

                report = run_intraday_pipeline(intraday_config)
                for rec in report.recommendations:
                    intraday_flags[rec.symbol] = rec.action
                message = format_intraday_plays(report, cycle_index)
                key = f"intraday_{cycle_index}"
                phase_messages[key] = message
                _deliver(
                    message,
                    f"Trading Desk — cycle {cycle_index}",
                    config=config,
                    discord=discord,
                    log=log,
                    posts=posts,
                )
            if intraday_flags:
                save_intraday_flags(session_dir, intraday_flags)

        elif phase_kind == DeskPhaseKind.PERFORMANCE:
            phase = schedule.phases[5]
            _wait_until(phase.scheduled_at, wait=wait, sleep=sleep, log=log, label=phase.label)
            perf_config = PerformanceConfig.from_env()
            perf_config.fixture_mode = config.fixture_mode
            perf_report = run_performance_pipeline(perf_config)
            save_performance_report(perf_report, session_dir)
            message = format_performance_plays(perf_report)
            phase_messages["performance"] = message
            _deliver(message, phase.label, config=config, discord=discord, log=log, posts=posts)

        elif phase_kind == DeskPhaseKind.CIO_REVIEW:
            if not config.include_cio:
                continue
            phase = schedule.phases[6]
            _wait_until(phase.scheduled_at, wait=wait, sleep=sleep, log=log, label=phase.label)
            cio_config = CIOConfig.from_env()
            cio_config.fixture_mode = config.fixture_mode
            cio_config.portfolio_value = config.portfolio_value
            cio_config.session_dir = str(session_dir)
            cio_config.cio_mode = "review"
            cio_report = run_cio_pipeline(cio_config)
            message = format_cio_review(cio_report)
            phase_messages["cio_review"] = message
            _deliver(message, phase.label, config=config, discord=discord, log=log, posts=posts)

    return SessionResult(
        trading_date=trading_date.isoformat(),
        schedule_log=schedule_log,
        phase_messages=phase_messages,
        plan_context_path=str(plan_path or session_dir / "daily_plan_context.json"),
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