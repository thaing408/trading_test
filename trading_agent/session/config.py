"""Configuration for full-day trading session orchestration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

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
    # trading_test / paper fork: CIO off by default (research → book, no approval board)
    include_cio: bool = False
    portfolio_value: float = 100_000.0
    log_file: str | None = None
    from_phase: DeskPhaseKind | None = None
    until_phase: DeskPhaseKind | None = None
    # Light discovery rescreens at fixed PT slots during RTH (see schedule.DISCOVERY_*)
    enable_discovery_refresh: bool = True
    # Each intraday cycle: watch gap_screener_book.json for updates / new continuation names
    enable_gap_book_watch: bool = True
    # When CIO is off, export research plan straight to auto_trade_book after research
    auto_export_book_without_cio: bool = True
    # Swing + multi-method at research (05:00 PT) and evening_scan (18:00 ET)
    enable_desk_scanners: bool = True
    enable_evening_scan: bool = True
    desk_scanner_limit: int = 20
    desk_scanner_multi_method: bool = True

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
        # Default OFF for this fork. Opt-in: TRADING_AGENT_INCLUDE_CIO=1
        include_cio = os.getenv("TRADING_AGENT_INCLUDE_CIO", "0").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        # Explicit kill-switch aliases
        if os.getenv("TRADING_AGENT_NO_CIO", "").strip().lower() in ("1", "true", "yes", "on"):
            include_cio = False
        auto_export = os.getenv("TRADING_AGENT_AUTO_EXPORT_WITHOUT_CIO", "1").strip().lower() not in (
            "0",
            "false",
            "no",
            "off",
        )
        desk_scan = os.getenv("TRADING_AGENT_DESK_SCANNERS", "1").lower() not in (
            "0",
            "false",
            "no",
            "off",
        )
        evening = os.getenv("TRADING_AGENT_EVENING_SCAN", "1").lower() not in (
            "0",
            "false",
            "no",
            "off",
        )
        multi = os.getenv("TRADING_AGENT_DESK_MULTI_METHOD", "1").lower() not in (
            "0",
            "false",
            "no",
            "off",
        )
        scan_lim = int(os.getenv("TRADING_AGENT_DESK_SCANNER_LIMIT", "20") or 20)
        wait = os.getenv("TRADING_AGENT_WAIT_FOR_SCHEDULE", "1").strip().lower() not in (
            "0",
            "false",
            "no",
            "off",
        )
        if os.getenv("PAPER_NO_WAIT", "").strip().lower() in ("1", "true", "yes", "on"):
            wait = False
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
            wait_for_schedule=wait,
            until_phase=until_phase,
            from_phase=from_phase,
            enable_discovery_refresh=disc,
            enable_gap_book_watch=gap_watch,
            include_cio=include_cio,
            auto_export_book_without_cio=auto_export,
            enable_desk_scanners=desk_scan,
            enable_evening_scan=evening,
            desk_scanner_limit=max(1, scan_lim),
            desk_scanner_multi_method=multi,
        )
