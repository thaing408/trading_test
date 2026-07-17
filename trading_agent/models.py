"""Shared data models for the trading agent pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MarketSnapshot:
    """Overnight institutional market snapshot.

    Optional groups (etfs, treasury_yields, breadth, unavailable) may be empty
    when a live series cannot be fetched; callers must not invent values.
    """

    source: str
    futures: Dict[str, Any] = field(default_factory=dict)
    international: Dict[str, Any] = field(default_factory=dict)
    bonds: Dict[str, Any] = field(default_factory=dict)
    dollar_index: Dict[str, Any] = field(default_factory=dict)
    vix: Dict[str, Any] = field(default_factory=dict)
    commodities: Dict[str, Any] = field(default_factory=dict)
    crypto: Dict[str, Any] = field(default_factory=dict)
    sector_rotation: Dict[str, Any] = field(default_factory=dict)
    etfs: Dict[str, Any] = field(default_factory=dict)
    treasury_yields: Dict[str, Any] = field(default_factory=dict)
    # breadth keys map to {status, value?, note?} — status is "ok" or "unavailable"
    breadth: Dict[str, Any] = field(default_factory=dict)
    # Named series that could not be sourced (e.g. MOVE, CME FedWatch, TRIN)
    unavailable: Dict[str, str] = field(default_factory=dict)
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
    avg_daily_volume: int = 0
    market_cap: float = 0.0  # 0 = unknown / not provided
    institutional_score: float = 0.0
    options_volume: int = 0
    # Pre-market observe/prepare fields (optional; 0 = not provided)
    gap_pct: float = 0.0
    premarket_relative_volume: float = 0.0


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
    ema_9: float = 0.0
    ema_20: float = 0.0
    ema_50: float = 0.0
    ema_200: float = 0.0
    breakout_state: str = "none"  # breakout | breakdown | none
    momentum: str = "neutral"  # bullish | bearish | neutral
    # Candlestick + institutional PA (PenguinBTC cheat-sheet proxies)
    candle_patterns: List[str] = field(default_factory=list)
    pa_signals: List[str] = field(default_factory=list)
    pattern_summary: str = "none"
    pattern_notes: List[str] = field(default_factory=list)


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
    probability_of_touch: float = 0.0
    options_volume: int = 0
    open_interest: int = 0
    bid_ask_spread_pct: float = 0.0


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
    direction: str = "Neutral"
    trade_thesis: str = ""
    trade_quality_score: float = 0.0
    risks: List[str] = field(default_factory=list)
    # Setup letter grade (A+/A/B/C/F) — A/A+ ranked first; drives PT/SL geometry
    setup_grade: str = "C"
    grade_score: float = 0.0
    hold_style: str = ""
    grade_reasons: List[str] = field(default_factory=list)
    # Book discipline: named playbook + checklist + edge completeness
    playbook_setup_id: str = ""
    playbook_name: str = ""
    checklist_passed: bool = False
    checklist_summary: str = ""
    edge_complete: bool = False
    edge_summary: str = ""
    mtf_gate_reason: str = ""
    # Fundamentals + blended quality (research → Mac auto_trade_book)
    fundamental_score: float = 0.0
    fundamental_passed: bool = True
    fundamental_summary: str = ""
    combined_quality_score: float = 0.0
    auto_trade_eligible: bool = False
    # Web/process method tags that supported or rejected the setup
    method_tags: List[str] = field(default_factory=list)
    method_notes: str = ""
    # Options-specific package (research → Mac ENTER)
    options_strategy_class: str = ""  # credit | debit | other
    iv_rank: float = 0.0
    options_pop: float = 0.0
    options_delta: float = 0.0
    expiration_days: int = 0
    defined_risk: bool = True
    options_method_notes: str = ""
    # Brandt LFD / TechCharts structure geometry (prefer over hardcoded %)
    stop_basis: str = ""  # lfd | negation | support | resistance | atr
    target_basis: str = ""  # measured_move | resistance | support | atr
    geometry_source: str = ""  # structure_lfd | structure_negation | hybrid | atr_blend
    risk_policy: str = ""  # lfd_tight | negation_structure | hybrid
    lfd_level: float = 0.0
    breakout_level: float = 0.0
    negation_level: float = 0.0
    measured_target: float = 0.0
    pattern_height: float = 0.0
    structure_notes: str = ""
    breakout_type: str = ""  # type_1_momentum … type_4_failed | unknown (live path)


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
    # Optional Raschke first-30m / PDL day bias (dict or DayBiasResult)
    day_bias: Any = None
