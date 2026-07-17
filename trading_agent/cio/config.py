"""Configuration for CIO decision agent."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class CIOConfig:
    fixture_mode: bool = False
    inputs_file: str | None = None
    output_file: str | None = None
    session_dir: str | None = None
    cio_mode: str = "approval"
    portfolio_value: float = 100_000.0
    min_risk_reward: float = 2.0
    min_probability: float = 0.50
    min_confidence: float = 60.0
    min_technical_confirmations: int = 3
    min_open_interest: int = 500
    min_options_volume: int = 1000
    max_bid_ask_spread_pct: float = 3.0
    min_liquidity_score: float = 50.0
    max_single_position_pct: float = 15.0
    max_sector_pct: float = 35.0
    max_strategy_pct: float = 40.0
    max_daily_loss_pct: float = 2.0
    max_portfolio_drawdown_pct: float = 10.0
    min_cash_pct: float = 20.0

    @classmethod
    def from_env(cls) -> "CIOConfig":
        fixture = os.getenv("TRADING_AGENT_FIXTURE", "").lower() in ("1", "true", "yes")
        conf = float(os.getenv("TRADING_AGENT_CIO_MIN_CONFIDENCE", "60") or 60)
        # Align CIO slightly with research when slight-less-cash A/B is on
        if os.getenv("TRADING_AGENT_SLIGHT_LESS_CASH", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        ) and os.getenv("TRADING_AGENT_CIO_MIN_CONFIDENCE") is None:
            conf = 55.0
        return cls(
            fixture_mode=fixture,
            inputs_file=os.getenv("TRADING_AGENT_CIO_INPUTS"),
            session_dir=os.getenv("TRADING_AGENT_SESSION_DIR"),
            output_file=os.getenv("TRADING_AGENT_OUTPUT"),
            portfolio_value=float(os.getenv("TRADING_AGENT_PORTFOLIO_VALUE", "100000")),
            min_confidence=conf,
        )