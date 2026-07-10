"""Central configuration for the pre-market trading agent."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class RiskConfig:
    """Institutional Trading Research floors (prompt minimums)."""

    max_risk_per_trade_pct: float = 2.0
    min_probability_of_success: float = 0.45
    min_confidence_score: float = 55.0
    max_bid_ask_spread_pct: float = 3.0  # tight bid/ask
    min_open_interest: int = 1_000
    min_volume: int = 2_000_000  # session volume floor
    min_avg_daily_volume: int = 2_000_000
    min_relative_volume: float = 2.0
    min_options_liquidity_score: float = 50.0
    min_price: float = 20.0
    min_market_cap: float = 2_000_000_000.0  # $2B
    min_institutional_score: float = 40.0
    min_technical_score: float = 40.0
    top_watchlist_size: int = 10
    top_candidates: int = 5


@dataclass
class ScreenerConfig:
    symbols: List[str] = field(
        default_factory=lambda: [
            "SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT", "NVDA", "AMZN", "META",
            "GOOGL", "TSLA", "AMD", "JPM", "XLE", "XLF", "XLK", "SMH", "SOXX",
            "XBI", "GLD", "TLT",
        ]
    )
    min_price: float = 20.0
    max_price: float = 10_000.0
    min_avg_daily_volume: int = 2_000_000
    min_relative_volume: float = 2.0
    min_market_cap: float = 2_000_000_000.0
    min_open_interest: int = 1_000
    max_bid_ask_spread_pct: float = 3.0


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