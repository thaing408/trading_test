"""Central configuration for the pre-market trading agent."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class RiskConfig:
    max_risk_per_trade_pct: float = 2.0
    min_probability_of_success: float = 0.45
    min_confidence_score: float = 55.0
    max_bid_ask_spread_pct: float = 5.0
    min_open_interest: int = 100
    min_volume: int = 50_000
    min_relative_volume: float = 1.2
    min_options_liquidity_score: float = 40.0


@dataclass
class ScreenerConfig:
    symbols: List[str] = field(
        default_factory=lambda: [
            "SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "AMZN", "META",
            "GOOGL", "TSLA", "AMD", "JPM", "XLE", "XLF", "GLD", "TLT",
        ]
    )
    min_price: float = 10.0
    max_price: float = 500.0


@dataclass
class AgentConfig:
    use_live_data: bool = True
    fixture_mode: bool = False
    output_file: str | None = None
    risk: RiskConfig = field(default_factory=RiskConfig)
    screener: ScreenerConfig = field(default_factory=ScreenerConfig)

    @classmethod
    def from_env(cls) -> "AgentConfig":
        fixture = os.getenv("TRADING_AGENT_FIXTURE", "").lower() in ("1", "true", "yes")
        live = os.getenv("TRADING_AGENT_LIVE", "1").lower() not in ("0", "false", "no")
        output = os.getenv("TRADING_AGENT_OUTPUT")
        return cls(
            use_live_data=live and not fixture,
            fixture_mode=fixture,
            output_file=output,
        )