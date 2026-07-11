"""Data models for CIO final decision process."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

DECISION_TYPES = (
    "Approve",
    "Approve with Modifications",
    "Delay",
    "Watchlist Only",
    "Reject",
)


@dataclass
class TradeCandidate:
    symbol: str
    direction: str
    strategy: str
    entry_price: float
    strike_prices: List[float]
    expiration: str
    profit_target: float
    stop_loss: float
    maximum_risk: float
    maximum_reward: float
    probability_of_success: float
    confidence_score: float
    primary_catalyst: str
    catalyst_type: str
    technical_summary: str
    technical_confirmations: List[str]
    options_summary: str
    open_interest: int
    daily_options_volume: int
    bid_ask_spread_pct: float
    iv_rank: float
    expected_move_pct: float
    probability_of_profit: float
    liquidity_score: float
    sector: str
    market_cap_tier: str = "large"
    correlation_group: str = ""
    phase1_rank: int = 0
    setup_grade: str = "C"
    grade_score: float = 0.0
    hold_style: str = ""


@dataclass
class PhaseContext:
    overall_market_bias: str
    market_environment_score: float
    market_regime: str
    stay_in_cash: bool = False
    intraday_flags: Dict[str, str] = field(default_factory=dict)
    strategy_refinement: Dict[str, float] = field(default_factory=dict)
    sector_refinement: Dict[str, float] = field(default_factory=dict)
    weakest_strategies: List[str] = field(default_factory=list)
    performance_notes: List[str] = field(default_factory=list)
    # Optional sector strength map (e.g. XLK: +0.5) from MI when available
    sector_strength: Dict[str, float] = field(default_factory=dict)


@dataclass
class EvaluationScorecard:
    market_fit: float
    catalyst_valid: bool
    catalyst_notes: str
    technical_confirmations: int
    technical_pass: bool
    technical_notes: str
    options_pass: bool
    options_notes: str
    risk_reward_ratio: float
    risk_pass: bool
    risk_notes: str
    challenges: List[str] = field(default_factory=list)
    # Expanded institutional challenge dimensions
    sector_strength_pass: bool = True
    sector_notes: str = ""
    correlation_notes: str = ""
    capital_efficiency: float = 0.0
    capital_efficiency_notes: str = ""
    estimated_trade_drawdown_pct: float = 0.0
    hedge_fund_standard: bool = False
    hedge_fund_notes: str = ""
    conviction_score: float = 0.0


@dataclass
class ApprovedTrade:
    ticker: str
    direction: str
    strategy: str
    entry_price: float
    strike_prices: List[float]
    expiration_date: str
    position_size_pct: float
    dollar_allocation: float
    maximum_risk: float
    maximum_reward: float
    profit_targets: List[float]
    stop_loss: float
    exit_criteria: str
    estimated_holding_period: str
    probability_of_success: float
    confidence_score: float
    risk_rating: str
    primary_catalyst: str
    technical_summary: str
    options_summary: str
    key_risks: List[str]
    contingency_plan: str
    decision: str
    decision_explanation: str
    sector: str = ""
    modifications: List[str] = field(default_factory=list)
    # CIO institutional challenge answers
    conviction_rank: int = 0
    conviction_score: float = 0.0
    why_it_works: str = ""
    why_it_fails: str = ""
    thesis_invalidation: str = ""
    hedge_fund_approve: str = ""
    reward_to_risk: float = 0.0
    capital_efficiency: float = 0.0
    estimated_drawdown_pct: float = 0.0
    correlation_group: str = ""
    setup_grade: str = "C"
    grade_score: float = 0.0
    hold_style: str = ""


@dataclass
class RejectedDecision:
    ticker: str
    decision: str
    explanation: str
    challenges: List[str]
    why_it_fails: str = ""
    thesis_invalidation: str = ""
    hedge_fund_approve: str = "No"


@dataclass
class PortfolioSummary:
    overall_market_bias: str
    market_environment_score: float
    total_capital_recommended_pct: float
    cash_allocation_pct: float
    approved_count: int
    rejected_count: int
    sector_allocation: Dict[str, float]
    strategy_allocation: Dict[str, float]
    average_probability: float
    average_confidence: float
    portfolio_risk_rating: str
    # Expanded allocation / risk
    modified_count: int = 0
    max_sector_concentration_pct: float = 0.0
    max_strategy_concentration_pct: float = 0.0
    estimated_portfolio_drawdown_pct: float = 0.0
    capital_efficiency_score: float = 0.0
    overall_portfolio_risk: str = "Low"
    correlation_note: str = ""


@dataclass
class CIOReport:
    date: str
    context: PhaseContext
    approved: List[ApprovedTrade]
    rejected: List[RejectedDecision]
    portfolio: PortfolioSummary
    governance_notes: List[str]
    metadata: Dict[str, str] = field(default_factory=dict)
    modified: List[ApprovedTrade] = field(default_factory=list)
