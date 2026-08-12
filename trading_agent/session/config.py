"""Configuration for full-day trading session orchestration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from trading_agent.product import include_cio_default, product_mode
from trading_agent.session.schedule import DeskPhaseKind


@dataclass
class SessionConfig:
    fixture_mode: bool = False
    dry_run: bool = False
    no_discord: bool = False
    trading_date: date | None = None
    timezone: str = "America/Los_Angeles"
    intraday_interval_minutes: int = 15
    # While open positions exist, PT/SL re-check more often than baseline (minutes)
    intraday_in_position_interval_minutes: int = 3
    intraday_cycles: int = 1
    positions_file: str | None = None
    session_file: str | None = None
    plan_file: str | None = None
    session_dir: Path | None = None
    wait_for_schedule: bool = True
    # trading_test default: False (methods lab). trading_agent desk: True.
    include_cio: bool = False
    # methods = multi-method primary research, no CIO decisions
    # desk = classic pipeline + CIO (live agent repo)
    product_mode: str = "methods"
    portfolio_value: float = 100_000.0
    log_file: str | None = None
    from_phase: DeskPhaseKind | None = None
    until_phase: DeskPhaseKind | None = None
    # Light discovery rescreens at fixed PT slots during RTH (see schedule.DISCOVERY_*)
    enable_discovery_refresh: bool = True
    # Each intraday cycle: watch gap_screener_book.json for updates / new continuation names
    enable_gap_book_watch: bool = True
    methods_scan_limit: int = 20

    @classmethod
    def from_env(cls) -> "SessionConfig":
        fixture = os.getenv("TRADING_AGENT_FIXTURE", "").lower() in ("1", "true", "yes")
        dry = os.getenv("TRADING_AGENT_DRY_RUN", "").lower() in ("1", "true", "yes")
        no_discord = os.getenv("TRADING_AGENT_NO_DISCORD", "").lower() in ("1", "true", "yes")
        interval = int(os.getenv("TRADING_AGENT_INTRADAY_INTERVAL", "15"))
        in_pos = int(
            os.getenv(
                "TRADING_AGENT_INTRADAY_IN_POSITION_INTERVAL",
                os.getenv("TRADING_AGENT_INTRADAY_POSITION_INTERVAL", "3"),
            )
        )
        cycles = int(os.getenv("TRADING_AGENT_INTRADAY_CYCLES", "1"))
        tz = os.getenv("TRADING_AGENT_TIMEZONE", "America/Los_Angeles")
        until_raw = os.getenv("TRADING_AGENT_UNTIL_PHASE", "").strip()
        until_phase = DeskPhaseKind(until_raw) if until_raw else None
        from_raw = os.getenv("TRADING_AGENT_FROM_PHASE", "").strip()
        from_phase = DeskPhaseKind(from_raw) if from_raw else None
        disc = os.getenv("TRADING_AGENT_DISCOVERY_REFRESH", "1").lower() not in (
            "0",
            "false",
            "no",
            "off",
        )
        gap_watch = os.getenv("TRADING_AGENT_GAP_BOOK_WATCH", "1").lower() not in (
            "0",
            "false",
            "no",
            "off",
        )
        mode = product_mode()
        # Methods lab: discovery still ok but never promotes CIO
        if mode == "methods" and not os.getenv("TRADING_AGENT_DISCOVERY_REFRESH"):
            disc = False
        limit = int(os.getenv("TRADING_TEST_SCAN_LIMIT", os.getenv("TRADING_AGENT_METHODS_LIMIT", "20")) or 20)
        return cls(
            fixture_mode=fixture,
            dry_run=dry,
            no_discord=no_discord,
            timezone=tz,
            intraday_interval_minutes=interval,
            intraday_in_position_interval_minutes=max(1, in_pos),
            intraday_cycles=cycles,
            positions_file=os.getenv("TRADING_AGENT_POSITIONS_FILE"),
            session_file=os.getenv("TRADING_AGENT_SESSION_FILE"),
            plan_file=os.getenv("TRADING_AGENT_PLAN_FILE"),
            log_file=os.getenv("TRADING_AGENT_SESSION_LOG"),
            until_phase=until_phase,
            from_phase=from_phase,
            include_cio=include_cio_default(),
            product_mode=mode,
            enable_discovery_refresh=disc,
            enable_gap_book_watch=gap_watch,
            methods_scan_limit=max(1, limit),
        )