"""CLI entry point for trading agent (pre-market + intraday)."""

from __future__ import annotations

import argparse
import sys

from trading_agent.config import AgentConfig
from trading_agent.intraday.config import IntradayConfig
from trading_agent.intraday.pipeline import run_intraday_pipeline
from trading_agent.intraday.reporter import render_intraday_report
from trading_agent.performance.config import PerformanceConfig
from trading_agent.performance.pipeline import run_performance_pipeline
from trading_agent.performance.reporter import render_performance_report
from trading_agent.pipeline import run_pipeline
from trading_agent.reporter.plan import render_daily_plan


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Trading Agent — Pre-Market, Intraday & Performance")
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

    parser.add_argument("--fixture", action="store_true", help="(legacy) fixture mode for premarket")
    parser.add_argument("--output", "-o", metavar="FILE", help="(legacy) output file")

    args = parser.parse_args(argv)

    if args.command == "intraday":
        return _run_intraday(args)
    if args.command == "performance":
        return _run_performance(args)
    if args.command == "premarket":
        return _run_premarket(args)

    return _run_premarket(args)


if __name__ == "__main__":
    sys.exit(main())