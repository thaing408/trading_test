"""Machine-usable TradingView-style screener parameter sets.

Derived from Julian Komar (@BlogJulianKomar) public material:
- Video #1 "Best Stock Screener for Growth & Momentum" (TradingView)
- Related posts: EMA 8/21, 52w strength, ADR, dollar-volume liquidity
- Pre-market intent: gap-ups + unusual relative volume (observe/prepare, not auto-buy)

Institutional agent floors (price ≥ $20, ADV ≥ 2M, mcap ≥ $2B, etc.) remain
separate in RiskConfig/ScreenerConfig and are applied *in addition* to these
strength gates — not replaced by them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class BestWinnersParams:
    """Growth & momentum "Best Winners" strength screen (TradingView-oriented)."""

    name: str = "best_winners"
    source: str = (
        "Julian Komar TradingView growth/momentum screener "
        "(ADR%, 52w low distance, EMA 8/21, 3m performance, dollar volume)"
    )
    market: str = "US"
    # Komar video often uses a soft $1 floor on TV; agent still enforces institutional price floor separately.
    min_price: float = 1.0
    min_adr_pct: float = 4.5
    adr_lookback: int = 20
    min_pct_above_52w_low: float = 70.0
    ema_fast: int = 8
    ema_slow: int = 21
    require_price_above_ema_fast: bool = True
    require_price_above_ema_slow: bool = True
    min_performance_3m_pct: float = 0.0  # 3-month performance > 0%
    performance_lookback_bars: int = 63  # ~3 months of trading days
    # price × avg 30d volume ≥ $10M
    min_dollar_volume_avg_30d: float = 10_000_000.0
    avg_volume_lookback: int = 30
    # price × prior-day volume ≥ $5M
    min_dollar_volume_prior_day: float = 5_000_000.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PreMarketParams:
    """Pre-market observe/prepare screen: gap-ups and unusual relative volume."""

    name: str = "pre_market"
    source: str = (
        "Julian Komar-style pre-market gap/unusual-volume prep "
        "(apply strength gates first; gap + RVOL for prioritization)"
    )
    market: str = "US"
    # Strength gates reused from Best Winners (same thresholds)
    apply_strength_gates: bool = True
    # Gap-up intent: positive open vs prior close (percent)
    min_gap_pct: float = 0.0  # gap-up: open above prior close
    # Unusual relative volume (session or pre-market proxy)
    min_relative_volume: float = 1.5
    prioritize_by: tuple = ("gap_pct", "relative_volume")
    auto_buy: bool = False  # observe/prepare only

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["prioritize_by"] = list(self.prioritize_by)
        return d


@dataclass
class ScreenerParameterSets:
    """Named parameter profiles available to the agent."""

    best_winners: BestWinnersParams = field(default_factory=BestWinnersParams)
    pre_market: PreMarketParams = field(default_factory=PreMarketParams)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "best_winners": self.best_winners.to_dict(),
            "pre_market": self.pre_market.to_dict(),
            "notes": {
                "institutional_floors": (
                    "RiskConfig/ScreenerConfig still enforce price≥$20, ADV≥2M, "
                    "RVOL≥2, mcap≥$2B, options floors — combined with strength gates."
                ),
                "usage": "pre-market pipeline applies strength gates with named rejection reasons",
            },
        }

    def list_profiles(self) -> List[str]:
        return ["best_winners", "pre_market"]


DEFAULT_SCREENER_PARAMS = ScreenerParameterSets()


def get_screener_params() -> ScreenerParameterSets:
    """Return the canonical named parameter sets (immutable defaults)."""
    return DEFAULT_SCREENER_PARAMS
