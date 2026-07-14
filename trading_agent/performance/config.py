"""Configuration for performance review."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class PerformanceConfig:
    fixture_mode: bool = False
    trades_file: str | None = None
    history_file: str | None = None
    output_file: str | None = None
    min_trades_for_refinement: int = 3
    max_confidence_adjustment: float = 10.0

    @classmethod
    def from_env(cls) -> "PerformanceConfig":
        fixture = os.getenv("TRADING_AGENT_FIXTURE", "").lower() in ("1", "true", "yes")
        trades = os.getenv("TRADING_AGENT_TRADES_FILE", "").strip() or None
        if not trades and not fixture:
            # Prefer local journal if present (Mac or Windows solo — not work↔home sync)
            try:
                from trading_agent.journal.trades import journal_path_for

                jp = journal_path_for()
                if jp.exists():
                    trades = str(jp)
            except Exception:
                pass
        return cls(
            fixture_mode=fixture,
            trades_file=trades,
            history_file=os.getenv("TRADING_AGENT_HISTORY_FILE"),
            output_file=os.getenv("TRADING_AGENT_OUTPUT"),
        )