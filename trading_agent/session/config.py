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
    intraday_cycles: int = 1
    positions_file: str | None = None
    session_file: str | None = None
    plan_file: str | None = None
    session_dir: Path | None = None
    wait_for_schedule: bool = True
    include_cio: bool = True
    portfolio_value: float = 100_000.0
    log_file: str | None = None
    from_phase: DeskPhaseKind | None = None
    until_phase: DeskPhaseKind | None = None

    @classmethod
    def from_env(cls) -> "SessionConfig":
        fixture = os.getenv("TRADING_AGENT_FIXTURE", "").lower() in ("1", "true", "yes")
        dry = os.getenv("TRADING_AGENT_DRY_RUN", "").lower() in ("1", "true", "yes")
        no_discord = os.getenv("TRADING_AGENT_NO_DISCORD", "").lower() in ("1", "true", "yes")
        interval = int(os.getenv("TRADING_AGENT_INTRADAY_INTERVAL", "15"))
        cycles = int(os.getenv("TRADING_AGENT_INTRADAY_CYCLES", "1"))
        tz = os.getenv("TRADING_AGENT_TIMEZONE", "America/Los_Angeles")
        until_raw = os.getenv("TRADING_AGENT_UNTIL_PHASE", "").strip()
        until_phase = DeskPhaseKind(until_raw) if until_raw else None
        return cls(
            fixture_mode=fixture,
            dry_run=dry,
            no_discord=no_discord,
            timezone=tz,
            intraday_interval_minutes=interval,
            intraday_cycles=cycles,
            positions_file=os.getenv("TRADING_AGENT_POSITIONS_FILE"),
            session_file=os.getenv("TRADING_AGENT_SESSION_FILE"),
            plan_file=os.getenv("TRADING_AGENT_PLAN_FILE"),
            log_file=os.getenv("TRADING_AGENT_SESSION_LOG"),
            until_phase=until_phase,
        )