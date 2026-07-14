"""Backtest result models and config variants."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class BacktestConfig:
    """Knobs that map to shipped RiskConfig / CIOConfig defaults."""

    name: str
    min_confidence_score: float = 55.0
    min_setup_grade: str = "C"
    prefer_a_tier_only: bool = False
    min_technical_score: float = 40.0
    min_probability_of_success: float = 0.45
    cio_min_confidence: float = 60.0
    cio_min_risk_reward: float = 2.0
    hold_bars: int = 5  # forward bars for deterministic fill model
    risk_per_trade_pct: float = 1.0  # % of portfolio risked per trade
    portfolio_value: float = 100_000.0
    max_trades_per_day: int = 3
    lookback_bars: int = 40  # history window for technicals
    # Book-discipline gates (SMB / Investopedia TA / playbook / MTF / rails)
    require_playbook_checklist: bool = True
    require_edge_package: bool = True
    enforce_mtf_gate: bool = True
    enforce_discipline_rails: bool = True
    enforce_smb_book_gates: bool = True
    enforce_ta_book_gates: bool = True
    # Simulate PST discovery refreshes: re-research N times per bar-day (1 = morning only)
    discovery_passes: int = 1


@dataclass
class SimulatedTrade:
    symbol: str
    strategy: str
    direction: str
    entry_price: float
    exit_price: float
    stop_loss: float
    profit_target: float
    entry_day_index: int
    exit_day_index: int
    exit_reason: str
    profit_loss: float
    grade: str = ""
    confidence: float = 0.0
    approved: bool = True


@dataclass
class DayResult:
    day_index: int
    candidates_screened: int
    research_opportunities: int
    cio_approved: int
    trades: List[SimulatedTrade] = field(default_factory=list)
    day_pnl: float = 0.0
    cash_pct: float = 100.0
    notes: str = ""


@dataclass
class BacktestPeriodResult:
    config_name: str
    config: BacktestConfig
    days: List[DayResult] = field(default_factory=list)
    trades: List[SimulatedTrade] = field(default_factory=list)
    total_pnl: float = 0.0
    win_rate: float = 0.0
    trade_count: int = 0
    winner_count: int = 0
    loser_count: int = 0
    expectancy: float = 0.0
    max_drawdown: float = 0.0
    profit_factor: float = 0.0
    avg_cash_pct: float = 100.0
    equity_curve: List[float] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SweepResult:
    results: List[BacktestPeriodResult]
    best_name: str
    objective: str
    ranking: List[str] = field(default_factory=list)
