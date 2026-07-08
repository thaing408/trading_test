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
        return cls(
            fixture_mode=fixture,
            trades_file=os.getenv("TRADING_AGENT_TRADES_FILE"),
            history_file=os.getenv("TRADING_AGENT_HISTORY_FILE"),
            output_file=os.getenv("TRADING_AGENT_OUTPUT"),
        )