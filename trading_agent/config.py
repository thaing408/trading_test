"""Central configuration for the pre-market trading agent."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

from trading_agent.screener.universe import default_expanded_universe, resolve_screener_symbols


@dataclass
class RiskConfig:
    """Institutional Trading Research floors (trade-path quality).

    Defaults validated by offline multi-regime backtest (`trading_agent.backtest`):
    strict_a_tier_book3 beat baseline C-book, high-confidence, and wide_book5 on
    capital-preservation score (higher expectancy, higher win rate, lower drawdown).
    wide_book5 had higher raw trade count but worse expectancy and deeper DD.

    Screener scan floors are looser (`ScreenerConfig`); these remain the trade bar.
    """

    max_risk_per_trade_pct: float = 2.0
    min_probability_of_success: float = 0.45
    min_confidence_score: float = 60.0  # backtest: 60 A-tier book > open conf-55 C-book
    max_bid_ask_spread_pct: float = 3.0  # tight bid/ask
    min_open_interest: int = 1_000
    min_volume: int = 2_000_000  # session volume floor
    min_avg_daily_volume: int = 2_000_000
    min_relative_volume: float = 2.0
    min_options_liquidity_score: float = 50.0
    min_price: float = 20.0
    min_market_cap: float = 2_000_000_000.0  # $2B
    min_institutional_score: float = 40.0
    min_technical_score: float = 45.0  # aligned with winning sweep arm
    top_watchlist_size: int = 20  # wider watchlist after expanded scan universe
    # backtest: book3 scored above book5 (less churn, lower max DD)
    top_candidates: int = 3
    # Letter grades: A+/A always ranked first. F is never a trade opportunity.
    min_setup_grade: str = "B"  # floor when not A-only; F still excluded
    prefer_a_tier_only: bool = True  # backtest winner: A+/A only
    # Book discipline rails (Douglas / Steenbarger / Bellafiore / Shannon)
    require_playbook_checklist: bool = True
    require_edge_package: bool = True
    enforce_mtf_gate: bool = True
    max_concurrent_plays: int = 3
    max_aggregate_risk_pct: float = 6.0
    stop_cooldown_minutes: int = 60
    enforce_discipline_rails: bool = True  # cool-down / concurrent / aggregate risk
    # SMB top-ten book gates (Livermore, Wizards, O'Neil, Dalton, Kiev, Kahneman…)
    enforce_smb_book_gates: bool = True
    oneil_min_rvol: float = 1.5
    oneil_min_rs: float = 0.0  # 0 = inactive RS floor
    # Investopedia TA books (Schwager, Pring, Murphy, Nison, Bulkowski…)
    # https://www.investopedia.com/articles/personal-finance/090916/top-5-books-learn-technical-analysis.asp
    enforce_ta_book_gates: bool = True
    ta_min_indicator_confluence: int = 2
    ta_pring_min_rvol: float = 1.2


@dataclass
class ScreenerConfig:
    """Scan-tier config: wide universe + softer floors than `RiskConfig` trade path.

    Symbols default to the expanded liquid universe (~90 names). Override via:
      TRADING_AGENT_SYMBOLS=AAPL,MSFT,...
      TRADING_AGENT_SYMBOLS_FILE=/path/to/list.txt
    """

    symbols: List[str] = field(default_factory=default_expanded_universe)
    # Scan floors (looser than RiskConfig trade floors)
    min_price: float = 10.0
    max_price: float = 10_000.0
    min_avg_daily_volume: int = 1_000_000  # scan: 1M ADV (trade path still 2M)
    min_relative_volume: float = 1.2  # scan: mild participation (trade path 2.0)
    min_market_cap: float = 1_000_000_000.0  # scan: $1B (trade path $2B)
    min_open_interest: int = 100  # scan soft OI; trade path still 1k
    max_bid_ask_spread_pct: float = 8.0  # scan: allow wider; trade path 3%
    # Drop only extreme illiquid at collector (fraction of scan ADV floor)
    hard_adv_fraction: float = 0.15
    # Apply scan RVOL as hard drop (False = keep low-RVOL names for watchlist)
    hard_rvol_filter: bool = False
    # Max symbols to fetch live (0 = no cap)
    max_symbols: int = 0
    # Concurrent Yahoo fetches (1 = sequential)
    fetch_workers: int = 6


@dataclass
class AgentConfig:
    use_live_data: bool = True
    fixture_mode: bool = False
    output_file: str | None = None
    risk: RiskConfig = field(default_factory=RiskConfig)
    screener: ScreenerConfig = field(default_factory=ScreenerConfig)
    # Komar-style strength gates
    apply_strength_gates: bool = True
    # hard = drop from research when strength fails (legacy)
    # soft = still analyze; prefer strength survivors on watchlist (more candidates)
    # off  = skip strength entirely
    strength_mode: str = "soft"
    apply_premarket_gap_rvol: bool = True
    # OHLCV for TR strength/technicals: auto | schwab | yfinance
    market_data_provider: str = "auto"

    @classmethod
    def from_env(cls) -> "AgentConfig":
        fixture = os.getenv("TRADING_AGENT_FIXTURE", "").lower() in ("1", "true", "yes")
        live = os.getenv("TRADING_AGENT_LIVE", "1").lower() not in ("0", "false", "no")
        output = os.getenv("TRADING_AGENT_OUTPUT")
        strength_env = os.getenv("TRADING_AGENT_STRENGTH_GATES", "1").lower()
        if strength_env in ("0", "false", "no", "off"):
            strength_on = False
            strength_mode = "off"
        elif strength_env in ("soft", "watchlist"):
            strength_on = True
            strength_mode = "soft"
        elif strength_env in ("hard", "strict", "1", "true", "yes"):
            # default improved path: soft when "1"/true for more candidates
            strength_on = True
            mode_override = os.getenv("TRADING_AGENT_STRENGTH_MODE", "soft").lower()
            strength_mode = mode_override if mode_override in ("hard", "soft", "off") else "soft"
        else:
            strength_on = True
            strength_mode = "soft"

        provider = (
            os.getenv("TRADING_AGENT_MARKET_DATA", "auto").strip().lower() or "auto"
        )
        symbols = resolve_screener_symbols()
        screener = ScreenerConfig(symbols=symbols)
        # Optional scan floor overrides
        if os.getenv("TRADING_AGENT_SCAN_MIN_RVOL"):
            screener.min_relative_volume = float(os.getenv("TRADING_AGENT_SCAN_MIN_RVOL", "1.2"))
        if os.getenv("TRADING_AGENT_SCAN_MIN_ADV"):
            screener.min_avg_daily_volume = int(os.getenv("TRADING_AGENT_SCAN_MIN_ADV", "1000000"))
        if os.getenv("TRADING_AGENT_SCAN_MAX_SYMBOLS"):
            screener.max_symbols = int(os.getenv("TRADING_AGENT_SCAN_MAX_SYMBOLS", "0"))

        return cls(
            use_live_data=live and not fixture,
            fixture_mode=fixture,
            output_file=output,
            apply_strength_gates=strength_on,
            strength_mode=strength_mode if strength_on else "off",
            market_data_provider=provider,
            screener=screener,
        )
