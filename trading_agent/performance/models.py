"""Data models for performance review and continuous improvement."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class CompletedTrade:
    symbol: str
    entry: float
    exit: float
    profit_loss: float
    holding_time_minutes: int
    strategy: str
    technical_setup: str
    news_catalyst: str
    market_conditions: str
    volatility_environment: str
    risk_reward_ratio: float
    probability_of_success: float
    confidence_score: float
    position_size: int
    max_drawdown: float
    max_favorable_excursion: float
    max_adverse_excursion: float
    sector: str = ""
    market_regime: str = ""
    entry_time: str = ""
    exit_time: str = ""
    indicator_combo: str = ""


@dataclass
class DailyMetrics:
    total_profit_loss: float
    win_rate: float
    average_winner: float
    average_loser: float
    profit_factor: float
    expectancy: float
    largest_winner: float
    largest_loser: float
    trade_count: int
    winner_count: int
    loser_count: int
    strategy_performance: Dict[str, float] = field(default_factory=dict)
    sector_performance: Dict[str, float] = field(default_factory=dict)
    regime_performance: Dict[str, float] = field(default_factory=dict)


@dataclass
class PatternInsights:
    best_strategies: List[str]
    weakest_strategies: List[str]
    losing_trade_causes: List[str]
    profitable_conditions: List[str]
    time_of_day_performance: Dict[str, float]
    top_indicator_combos: List[str]
    top_news_catalysts: List[str]


@dataclass
class ConfidenceRefinement:
    strategy_adjustments: Dict[str, float]
    sector_adjustments: Dict[str, float]
    regime_adjustments: Dict[str, float]
    notes: List[str]


@dataclass
class PerformanceReport:
    date: str
    trades: List[CompletedTrade]
    metrics: DailyMetrics
    patterns: PatternInsights
    refinement: ConfidenceRefinement
    lessons_learned: List[str]
    mistakes_to_avoid: List[str]
    areas_for_improvement: List[str]
    successful_habits: List[str]
    tomorrow_adjustments: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)