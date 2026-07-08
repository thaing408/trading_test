"""CLI entry point for the Pre-Market Research & Trade Planning Agent."""

from __future__ import annotations

import argparse
import sys

from trading_agent.config import AgentConfig
from trading_agent.pipeline import run_pipeline
from trading_agent.reporter.plan import render_daily_plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pre-Market Research & Trade Planning Agent — Daily Trading Plan"
    )
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="Use fixture data instead of live providers (deterministic testing)",
    )
    parser.add_argument(
        "--output",
        "-o",
        metavar="FILE",
        help="Write plan to file in addition to stdout",
    )
    args = parser.parse_args(argv)

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


if __name__ == "__main__":
    sys.exit(main())