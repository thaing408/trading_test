"""Orchestrate the full Pacific-time trading desk day."""

from __future__ import annotations

import sys
import time
import traceback
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
from trading_agent.intraday.plan_loader import load_positions
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
from trading_agent.session.discovery import (
    due_discovery_slots,
    format_discovery_refresh,
    run_discovery_refresh,
)
from trading_agent.session.intelligence import run_intelligence_pass
from trading_agent.session.play_formatter import (
    format_cio_plays,
    format_cio_review,
    format_intelligence_brief,
    format_intraday_discord_title,
    format_intraday_plays,
    should_post_intraday_discord,
    format_performance_plays,
    format_preopen_check,
    format_research_plays,
)
from trading_agent.runtime.stdio import configure_stdio, safe_write
from trading_agent.session.phase_runner import resolve_phase_window
from trading_agent.session.schedule import (
    PT,
    DeskPhaseKind,
    compute_desk_schedule,
    is_regular_session,
    next_intraday_interval_minutes,
    render_desk_schedule_log,
    resolve_trading_date,
    seconds_until,
)

SleepFn = Callable[[float], None]


def session_has_open_positions(config: SessionConfig) -> bool:
    """True when the desk can see one or more open positions (file/fixture/broker)."""
    try:
        positions = load_positions(config.positions_file, config.fixture_mode)
    except Exception:  # noqa: BLE001 — treat load failure as flat (baseline cadence)
        return False
    return len(positions) > 0


def resolve_intraday_wait_minutes(config: SessionConfig, *, has_open_positions: bool | None = None) -> int:
    """Shipped entry for adaptive PT/SL spacing (baseline vs in-position)."""
    if has_open_positions is None:
        has_open_positions = session_has_open_positions(config)
    return next_intraday_interval_minutes(
        config.intraday_interval_minutes,
        bool(has_open_positions),
        in_position_minutes=config.intraday_in_position_interval_minutes,
    )


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
    safe_write(handle, message)


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

    start_kind, phases_to_run = resolve_phase_window(config, current, schedule)
    if config.until_phase is not None:
        _log(log, f"Phase scope: {start_kind.value} -> {config.until_phase.value} ({len(phases_to_run)} phases)")
    if not phases_to_run:
        _log(
            log,
            f"[warn] No phases to run (start={start_kind.value}, until={getattr(config.until_phase, 'value', 'full day')}). "
            "Check TRADING_AGENT_FROM_PHASE / --from-phase.",
        )
        return SessionResult(
            trading_date=trading_date.isoformat(),
            schedule_log=schedule_log,
            phase_messages=phase_messages,
            plan_context_path=str(session_dir / "daily_plan_context.json"),
            discord_posts=posts,
        )

    _log(log, schedule_log)

    agent_config = AgentConfig.from_env()
    agent_config.fixture_mode = config.fixture_mode
    agent_config.use_live_data = not config.fixture_mode

    plan_path: Path | None = None
    plan_context: dict = {}
    watch_symbols: list[str] = []
    intraday_flags: dict[str, str] = {}

    for phase_kind in phases_to_run:
        try:
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
                # Fixture/dry-run: fixed small cycle count. Live wait: adaptive until close.
                fixed_cycles = config.intraday_cycles
                live_adaptive = wait and not config.fixture_mode and not config.dry_run
                if plan_path is None:
                    plan_path = session_dir / "daily_plan_context.json"
                # Cap adaptive cycles (baseline grid × ratio of intervals) to avoid runaway
                baseline = max(1, config.intraday_interval_minutes)
                fast = max(1, config.intraday_in_position_interval_minutes)
                max_live_cycles = max(
                    len(schedule.intraday_cycles) * max(1, baseline // min(fast, baseline) + 1),
                    len(schedule.intraday_cycles),
                    1,
                )
                cycle_index = 0
                discovery_done: set[str] = set()
                discovery_cio_promoted = False
                # Suppress Discord spam when PT/SL checks repeat the same actions
                last_intraday_fingerprint: str | None = None
                # Fixture/dry-run: fire one discovery after first cycle so path is exercised
                fixture_discovery_done = False
                while True:
                    cycle_index += 1
                    has_pos = session_has_open_positions(config)
                    wait_mins = resolve_intraday_wait_minutes(config, has_open_positions=has_pos)
                    try:
                        from trading_agent.intraday.manage_log import log_interval_decision

                        open_syms: list[str] = []
                        try:
                            from trading_agent.intraday.plan_loader import load_positions

                            open_syms = [
                                p.symbol
                                for p in load_positions(
                                    config.positions_file, config.fixture_mode
                                )
                                if p.symbol and p.quantity > 0
                            ]
                        except Exception:
                            open_syms = []
                        log_interval_decision(
                            cycle=cycle_index,
                            wait_minutes=wait_mins,
                            baseline_minutes=baseline,
                            in_position_minutes=fast,
                            has_open_positions=has_pos,
                            open_symbols=open_syms,
                        )
                    except Exception:
                        pass

                    if wait:
                        if cycle_index == 1:
                            # Align to desk open; if already open, start PT/SL check immediately
                            open_target = (
                                schedule.intraday_cycles[0]
                                if schedule.intraday_cycles
                                else schedule.market_open
                            )
                            _wait_until(
                                open_target,
                                wait=True,
                                sleep=sleep,
                                log=log,
                                label=f"Trading Desk open / cycle {cycle_index}",
                            )
                        else:
                            _log(
                                log,
                                f"Next PT/SL check in {wait_mins}m "
                                f"(baseline={baseline}m, in_position={fast}m, "
                                f"open_positions={has_pos})",
                            )
                            sleep(float(wait_mins * 60))
                            if not is_regular_session(datetime.now(tz), schedule):
                                _log(log, "Regular session closed — stopping intraday cycles.")
                                break
                    else:
                        # Dry/fixture: still compute and log what live wait would be
                        _log(
                            log,
                            f"[interval] cycle={cycle_index} next_wait_minutes={wait_mins} "
                            f"open_positions={has_pos} "
                            f"baseline={baseline} in_position={fast}",
                        )

                    # --- Gap book file watch: new continuation tickers → auto-trade prep ---
                    # Picks up researcher /gapscan updates between discovery slots.
                    if getattr(config, "enable_gap_book_watch", True):
                        try:
                            from trading_agent.export.gap_watch import check_and_process_gap_book

                            gap_res = check_and_process_gap_book(
                                agent_config,
                                session_dir=session_dir,
                                force=bool(
                                    config.fixture_mode
                                    and cycle_index == 1
                                    and not discovery_done
                                ),
                            )
                            if gap_res.triggered or (
                                gap_res.snapshot.changed and gap_res.snapshot.new_continuation
                            ):
                                gmsg = gap_res.discord_message or gap_res.snapshot.message
                                _log(log, f"[gap-watch] {gap_res.snapshot.message}")
                                if gap_res.enter_symbols:
                                    watch_symbols = list(
                                        dict.fromkeys(
                                            list(gap_res.enter_symbols)
                                            + list(watch_symbols)
                                            + list(gap_res.snapshot.continuation)
                                        )
                                    )
                                elif gap_res.snapshot.continuation:
                                    watch_symbols = list(
                                        dict.fromkeys(
                                            list(gap_res.snapshot.continuation)
                                            + list(watch_symbols)
                                        )
                                    )
                                if gmsg and (
                                    gap_res.triggered
                                    or gap_res.snapshot.new_continuation
                                    or gap_res.error
                                ):
                                    phase_messages[
                                        f"gap_watch_{cycle_index}"
                                    ] = gmsg
                                    _deliver(
                                        gmsg,
                                        f"Gap watch — cycle {cycle_index}",
                                        config=config,
                                        discord=discord,
                                        log=log,
                                        posts=posts,
                                    )
                            else:
                                _log(log, f"[gap-watch] {gap_res.snapshot.message}")
                        except Exception as gap_exc:  # noqa: BLE001
                            _log(log, f"[warn] Gap book watch failed: {gap_exc}")
                            _log(log, traceback.format_exc())

                    # --- Light discovery refresh at fixed PT slots (or once in fixture) ---
                    if getattr(config, "enable_discovery_refresh", True):
                        now_pt = datetime.now(tz)
                        slots = schedule.discovery_refreshes or ()
                        due = due_discovery_slots(slots, now=now_pt, already_run=discovery_done)
                        if (
                            not live_adaptive
                            and not fixture_discovery_done
                            and cycle_index >= 1
                            and slots
                        ):
                            # Dry/fixture: run first slot once so discovery path is covered
                            due = [slots[0]]
                            fixture_discovery_done = True
                        for slot in due:
                            key = slot.strftime("%H:%M")
                            label = f"Discovery refresh {key} PT"
                            _log(log, f"=== {label} ===")
                            try:
                                if plan_path and plan_path.exists():
                                    plan_context = load_saved_plan_context(plan_path)
                                disc = run_discovery_refresh(
                                    agent_config,
                                    session_dir=session_dir,
                                    prior_context=plan_context,
                                    slot_label=key + " PT",
                                    scheduled_at=slot,
                                    promote_cio=True,
                                    fixture_mode=config.fixture_mode,
                                    portfolio_value=config.portfolio_value,
                                    already_promoted=discovery_cio_promoted,
                                )
                                plan_context = disc.context
                                plan_path = session_dir / "daily_plan_context.json"
                                if disc.cio_promoted:
                                    discovery_cio_promoted = True
                                    for sym in disc.cio_approved:
                                        if sym not in watch_symbols:
                                            watch_symbols.append(sym)
                                    phase_messages[
                                        f"cio_discovery_{key.replace(':', '')}"
                                    ] = disc.cio_message or "CIO discovery promotion"
                                watch_symbols = list(
                                    dict.fromkeys(
                                        list(disc.watchlist)
                                        + list(watch_symbols)
                                        + list(disc.new_symbols)
                                    )
                                )
                                dmsg = format_discovery_refresh(disc)
                                phase_messages[f"discovery_{key.replace(':', '')}"] = dmsg
                                _deliver(
                                    dmsg,
                                    label,
                                    config=config,
                                    discord=discord,
                                    log=log,
                                    posts=posts,
                                )
                                if disc.cio_promoted and disc.cio_message:
                                    _deliver(
                                        disc.cio_message,
                                        f"CIO Discovery Promotion {key} PT",
                                        config=config,
                                        discord=discord,
                                        log=log,
                                        posts=posts,
                                    )
                            except Exception as disc_exc:  # noqa: BLE001
                                _log(log, f"[warn] Discovery refresh {key} failed: {disc_exc}")
                                _log(log, traceback.format_exc())
                            discovery_done.add(key)

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
                    try:
                        from trading_agent.intraday.manage_log import log_manage_recommendations

                        log_manage_recommendations(
                            cycle=cycle_index,
                            wait_minutes=wait_mins,
                            has_open_positions=has_pos,
                            recommendations=report.recommendations or [],
                        )
                    except Exception:
                        pass
                    message = format_intraday_plays(report, cycle_index)
                    key = f"intraday_{cycle_index}"
                    phase_messages[key] = message
                    title = format_intraday_discord_title(report, cycle_index)
                    post_discord, last_intraday_fingerprint = should_post_intraday_discord(
                        report,
                        cycle=cycle_index,
                        previous_fingerprint=last_intraday_fingerprint,
                    )
                    if post_discord:
                        _deliver(
                            message,
                            title,
                            config=config,
                            discord=discord,
                            log=log,
                            posts=posts,
                        )
                    else:
                        # Always keep full text in session log; skip Discord noise
                        _log(log, "")
                        _log(log, f"=== {title} (check #{cycle_index}, Discord quiet — unchanged) ===")
                        _log(log, message)

                    if live_adaptive:
                        if not is_regular_session(datetime.now(tz), schedule):
                            _log(log, "Regular session closed after cycle — stopping.")
                            break
                        if cycle_index >= max_live_cycles:
                            _log(log, f"Reached max adaptive cycles ({max_live_cycles}) — stopping.")
                            break
                    else:
                        if cycle_index >= fixed_cycles:
                            break
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
        except Exception as exc:
            label = phase_kind.value
            _log(log, f"[error] Phase {label} failed: {exc}")
            _log(log, traceback.format_exc())
            raise

    return SessionResult(
        trading_date=trading_date.isoformat(),
        schedule_log=schedule_log,
        phase_messages=phase_messages,
        plan_context_path=str(plan_path or session_dir / "daily_plan_context.json"),
        discord_posts=posts,
    )


def run_session_cli(config: SessionConfig) -> int:
    configure_stdio()
    log_path = config.log_file
    handle: TextIO | None = None
    if log_path:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        handle = open(log_path, "w", encoding="utf-8")
    try:
        result = run_session(config, log=handle or sys.stdout)
        if not result.phase_messages:
            _log(handle, "[warn] Session finished with no phase output")
            return 1
        return 0
    except Exception as exc:
        _log(handle, f"[fatal] Desk session aborted: {exc}")
        _log(handle, traceback.format_exc())
        return 1
    finally:
        if handle:
            handle.close()