"""Data models for intraday position management."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

ACTION_TYPES = (
    "Enter",
    "Hold",
    "Scale In",
    "Scale Out",
    "Adjust",
    "Roll",
    "Hedge",
    "Exit",
    "Take Partial Profit",
    "Move Stop Loss",
    "Take No Action",
)


@dataclass
class OpenPosition:
    symbol: str
    strategy: str
    entry_price: float
    stop_loss: float
    profit_target: float
    strike_prices: List[float]
    expiration: str
    quantity: int = 1
    thesis: str = ""
    original_probability: float = 0.5
    original_confidence: float = 60.0
    current_price: float = 0.0
    allows_averaging_down: bool = False
    trailing_stop_pct: float = 2.0
    max_risk_dollars: float = 500.0
    pending_entry: bool = False
    # Brandt LFD / TechCharts structure (from plan handoff; optional)
    direction: str = ""
    lfd_level: float = 0.0
    breakout_level: float = 0.0
    negation_level: float = 0.0
    measured_target: float = 0.0
    breakout_type: str = ""


@dataclass
class SymbolSessionData:
    symbol: str
    price: float
    change_pct: float
    vwap: float
    volume: int
    relative_volume: float
    support: float
    resistance: float
    trend: str
    momentum: str
    iv: float
    iv_change_pct: float
    open_interest: int
    oi_change_pct: float
    delta: float
    gamma: float
    theta: float
    vega: float
    options_flow_bias: str


@dataclass
class SessionSnapshot:
    source: str
    market_regime: str
    prior_regime: str
    vix: float
    vix_change_pct: float
    breadth_advancers: int
    breadth_decliners: int
    breadth_ratio: float
    sector_leaders: List[str]
    sector_laggards: List[str]
    symbols: Dict[str, SymbolSessionData] = field(default_factory=dict)
    breaking_news: List[str] = field(default_factory=list)
    economic_announcements: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class SessionSynthesis:
    regime_shift: bool
    regime_description: str
    observations: List[str]
    risk_environment: str
    session_score: float


@dataclass
class Alert:
    alert_type: str
    symbol: str
    message: str
    recommended_response: str
    severity: str = "high"


@dataclass
class PositionRecommendation:
    symbol: str
    action: str
    what_changed: str
    why_recommended: str
    risk_if_no_action: str
    updated_probability: float
    updated_confidence: float
    alerts: List[Alert] = field(default_factory=list)


@dataclass
class RiskLimitEvaluation:
    within_limits: bool
    breaches: List[str] = field(default_factory=list)


@dataclass
class IntradayReport:
    timestamp: str
    cycle_count: int
    session: SessionSynthesis
    session_snapshot: SessionSnapshot
    recommendations: List[PositionRecommendation]
    notifications: List[Alert]
    risk_evaluation: RiskLimitEvaluation
    plan_context: Dict[str, Any] = field(default_factory=dict)
    no_open_positions: bool = False