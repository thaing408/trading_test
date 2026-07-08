"""Shared data models for the trading agent pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MarketSnapshot:
    source: str
    futures: Dict[str, Any] = field(default_factory=dict)
    international: Dict[str, Any] = field(default_factory=dict)
    bonds: Dict[str, Any] = field(default_factory=dict)
    dollar_index: Dict[str, Any] = field(default_factory=dict)
    vix: Dict[str, Any] = field(default_factory=dict)
    commodities: Dict[str, Any] = field(default_factory=dict)
    crypto: Dict[str, Any] = field(default_factory=dict)
    sector_rotation: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


@dataclass
class CalendarEvent:
    time: str
    event: str
    impact: str
    country: str = "US"


@dataclass
class EconomicCalendar:
    source: str
    events: List[CalendarEvent] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class NewsItem:
    symbol: str
    headline: str
    source: str
    category: str


@dataclass
class NewsCatalysts:
    source: str
    items: List[NewsItem] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class ScreenerCandidate:
    symbol: str
    price: float
    volume: int
    relative_volume: float
    options_liquidity_score: float
    open_interest: int
    bid_ask_spread_pct: float
    sector: str = ""


@dataclass
class ScreenerResult:
    source: str
    candidates: List[ScreenerCandidate] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class TechnicalAnalysis:
    symbol: str
    trend: str
    rsi: float
    macd_signal: str
    adx: float
    atr: float
    bollinger_position: str
    support: float
    resistance: float
    relative_strength: float
    vwap_relation: str
    ma_alignment: str
    volume_profile_bias: str
    score: float
    timeframe_trends: Dict[str, str] = field(default_factory=dict)
    timeframe_alignment: str = "mixed"


@dataclass
class OptionsMetrics:
    symbol: str
    implied_volatility: float
    iv_rank: float
    iv_percentile: float
    expected_move_pct: float
    delta: float
    gamma: float
    theta: float
    vega: float
    unusual_activity: bool
    institutional_flow_bias: str
    liquidity_score: float
    probability_of_profit: float


@dataclass
class TradeOpportunity:
    rank: int
    symbol: str
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
    supporting_reasons: List[str]
    technical: TechnicalAnalysis
    options: OptionsMetrics


@dataclass
class RejectedSetup:
    symbol: str
    reason: str


@dataclass
class DailyTradingPlan:
    date: str
    overall_market_bias: str
    market_environment_score: float
    top_watchlist: List[str]
    ranked_opportunities: List[TradeOpportunity]
    rejection_reasons: List[RejectedSetup]
    research_summary: Dict[str, Any]
    stay_in_cash: bool
    cash_recommendation_reason: str = ""