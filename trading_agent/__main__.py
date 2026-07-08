"""CLI entry point for trading agent (pre-market + intraday)."""

from __future__ import annotations

import argparse
import sys

from trading_agent.config import AgentConfig
from trading_agent.intraday.config import IntradayConfig
from trading_agent.intraday.pipeline import run_intraday_pipeline
from trading_agent.intraday.reporter import render_intraday_report
from trading_agent.cio.config import CIOConfig
from trading_agent.cio.pipeline import run_cio_pipeline
from trading_agent.cio.reporter import render_cio_report
from trading_agent.performance.config import PerformanceConfig
from trading_agent.performance.pipeline import run_performance_pipeline
from trading_agent.performance.reporter import render_performance_report
from trading_agent.pipeline import run_pipeline
from trading_agent.reporter.plan import render_daily_plan
from trading_agent.session.config import SessionConfig
from trading_agent.session.orchestrator import run_session_cli
from trading_agent.session.schedule import DeskPhaseKind


def _run_premarket(args: argparse.Namespace) -> int:
    config = AgentConfig.from_env()
    if args.fixture:
        config.fixture_mode = True
        config.use_live_data = False
    if args.output:
        config.output_file = args.output

    plan = run_pipeline(config)
    report = render_daily_plan(plan)
    print(report)
    if config.output_file:
        with open(config.output_file, "w", encoding="utf-8") as f:
            f.write(report)
    return 0


def _run_intraday(args: argparse.Namespace) -> int:
    config = IntradayConfig.from_env()
    if args.fixture:
        config.fixture_mode = True
        config.use_live_data = False
    if args.plan:
        config.plan_file = args.plan
    if args.positions:
        config.positions_file = args.positions
    if args.session:
        config.session_file = args.session
    if args.output:
        config.output_file = args.output
    if args.cycles:
        config.cycles = args.cycles

    report = run_intraday_pipeline(config)
    text = render_intraday_report(report)
    print(text)
    if config.output_file:
        with open(config.output_file, "w", encoding="utf-8") as f:
            f.write(text)
    return 0


def _run_performance(args: argparse.Namespace) -> int:
    config = PerformanceConfig.from_env()
    if args.fixture:
        config.fixture_mode = True
    if args.trades:
        config.trades_file = args.trades
    if args.history:
        config.history_file = args.history
    if args.output:
        config.output_file = args.output

    report = run_performance_pipeline(config)
    text = render_performance_report(report)
    print(text)
    if config.output_file:
        with open(config.output_file, "w", encoding="utf-8") as f:
            f.write(text)
    return 0


def _run_session(args: argparse.Namespace) -> int:
    from datetime import date as date_type

    config = SessionConfig.from_env()
    if args.fixture:
        config.fixture_mode = True
    if args.dry_run:
        config.dry_run = True
    if args.no_discord:
        config.no_discord = True
    if args.date:
        config.trading_date = date_type.fromisoformat(args.date)
    if args.interval:
        config.intraday_interval_minutes = args.interval
    if args.cycles:
        config.intraday_cycles = args.cycles
    if args.positions:
        config.positions_file = args.positions
    if args.session:
        config.session_file = args.session
    if args.plan:
        config.plan_file = args.plan
    if args.output:
        config.log_file = args.output
    if args.no_cio:
        config.include_cio = False
    if args.portfolio_value:
        config.portfolio_value = args.portfolio_value

    if args.timezone:
        config.timezone = args.timezone
    if args.from_phase:
        config.from_phase = DeskPhaseKind(args.from_phase)

    if config.fixture_mode or config.dry_run or config.no_discord:
        config.wait_for_schedule = False

    return run_session_cli(config)


def _run_cio(args: argparse.Namespace) -> int:
    config = CIOConfig.from_env()
    if args.fixture:
        config.fixture_mode = True
    if args.inputs:
        config.inputs_file = args.inputs
    if args.output:
        config.output_file = args.output
    if args.portfolio_value:
        config.portfolio_value = args.portfolio_value

    report = run_cio_pipeline(config)
    text = render_cio_report(report)
    print(text)
    if config.output_file:
        with open(config.output_file, "w", encoding="utf-8") as f:
            f.write(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Trading Agent — Full Desk (Phases 1–4)")
    subparsers = parser.add_subparsers(dest="command")

    premarket = subparsers.add_parser("premarket", help="Generate Daily Trading Plan (Phase 1)")
    premarket.add_argument("--fixture", action="store_true", help="Use fixture data")
    premarket.add_argument("--output", "-o", metavar="FILE", help="Write report to file")

    intraday = subparsers.add_parser("intraday", help="Intraday position management (Phase 2)")
    intraday.add_argument("--fixture", action="store_true", help="Use fixture data")
    intraday.add_argument("--plan", metavar="FILE", help="Daily Trading Plan context JSON")
    intraday.add_argument("--positions", metavar="FILE", help="Open positions JSON")
    intraday.add_argument("--session", metavar="FILE", help="Intraday session fixture JSON")
    intraday.add_argument("--output", "-o", metavar="FILE", help="Write report to file")
    intraday.add_argument("--cycles", type=int, default=1, help="Monitoring cycle count")

    performance = subparsers.add_parser("performance", help="Performance review (Phase 3)")
    performance.add_argument("--fixture", action="store_true", help="Use fixture data")
    performance.add_argument("--trades", metavar="FILE", help="Completed trades JSON")
    performance.add_argument("--history", metavar="FILE", help="Historical trades JSON")
    performance.add_argument("--output", "-o", metavar="FILE", help="Write report to file")

    session = subparsers.add_parser(
        "session",
        help="Run full PST trading desk day (7 phases) with Discord delivery",
    )
    session.add_argument("--fixture", action="store_true", help="Use fixture data")
    session.add_argument("--dry-run", action="store_true", help="Run pipelines without Discord posts")
    session.add_argument("--no-discord", action="store_true", help="Skip Discord delivery")
    session.add_argument("--date", metavar="YYYY-MM-DD", help="Trading session date (default: next session)")
    session.add_argument(
        "--timezone",
        default="America/Los_Angeles",
        help="Desk schedule timezone (default: America/Los_Angeles)",
    )
    session.add_argument(
        "--from-phase",
        choices=[p.value for p in DeskPhaseKind],
        help="Start at a specific desk phase (skip earlier phases)",
    )
    session.add_argument("--interval", type=int, default=15, help="Intraday cycle interval in minutes")
    session.add_argument("--cycles", type=int, default=1, help="Intraday cycles to run (fixture/dry-run)")
    session.add_argument("--positions", metavar="FILE", help="Open positions JSON")
    session.add_argument("--session", metavar="FILE", help="Intraday session fixture JSON")
    session.add_argument("--plan", metavar="FILE", help="Existing plan context JSON (skip pre-market regeneration)")
    session.add_argument("--no-cio", action="store_true", help="Skip CIO summary push")
    session.add_argument("--portfolio-value", type=float, default=100_000, help="Portfolio value for CIO allocation")
    session.add_argument("--output", "-o", metavar="FILE", help="Write session log to file")

    cio = subparsers.add_parser("cio", help="CIO final decision (Phase 4)")
    cio.add_argument("--fixture", action="store_true", help="Use fixture data")
    cio.add_argument("--inputs", metavar="FILE", help="CIO inputs JSON (phases 1-3 context)")
    cio.add_argument("--portfolio-value", type=float, default=100_000, help="Portfolio value for allocation")
    cio.add_argument("--output", "-o", metavar="FILE", help="Write report to file")

    parser.add_argument("--fixture", action="store_true", help="(legacy) fixture mode for premarket")
    parser.add_argument("--output", "-o", metavar="FILE", help="(legacy) output file")

    args = parser.parse_args(argv)

    if args.command == "session":
        return _run_session(args)
    if args.command == "intraday":
        return _run_intraday(args)
    if args.command == "performance":
        return _run_performance(args)
    if args.command == "cio":
        return _run_cio(args)
    if args.command == "premarket":
        return _run_premarket(args)

    return _run_premarket(args)


if __name__ == "__main__":
    sys.exit(main())