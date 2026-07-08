"""Configuration for intraday position management."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class IntradayRiskConfig:
    max_loss_per_position_pct: float = 5.0
    max_portfolio_risk_pct: float = 10.0
    profit_target_tolerance_pct: float = 0.5
    stop_loss_tolerance_pct: float = 0.1
    trailing_stop_activation_pct: float = 1.5
    partial_profit_pct: float = 50.0
    regime_shift_penalty: float = 15.0
    better_opportunity_margin: float = 10.0
    roll_days_threshold: int = 14


@dataclass
class IntradayConfig:
    use_live_data: bool = True
    fixture_mode: bool = False
    plan_file: str | None = None
    positions_file: str | None = None
    session_file: str | None = None
    output_file: str | None = None
    cycles: int = 1
    risk: IntradayRiskConfig = field(default_factory=IntradayRiskConfig)
    watch_symbols: List[str] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> "IntradayConfig":
        fixture = os.getenv("TRADING_AGENT_FIXTURE", "").lower() in ("1", "true", "yes")
        live = os.getenv("TRADING_AGENT_LIVE", "1").lower() not in ("0", "false", "no")
        return cls(
            use_live_data=live and not fixture,
            fixture_mode=fixture,
            plan_file=os.getenv("TRADING_AGENT_PLAN_FILE"),
            positions_file=os.getenv("TRADING_AGENT_POSITIONS_FILE"),
            output_file=os.getenv("TRADING_AGENT_OUTPUT"),
        )