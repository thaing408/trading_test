"""Machine-usable TradingView-style screener parameter sets.

Derived from Julian Komar (@BlogJulianKomar) public material:
- Video #1 "Best Stock Screener for Growth & Momentum" (TradingView)
- Related posts: EMA 8/21, 52w strength, ADR, dollar-volume liquidity
- Pre-market intent: gap-ups + unusual relative volume (observe/prepare, not auto-buy)

Default profile is **softened** for large-cap / quieter regimes so ADR/52w/EMA
do not mass-reject the watchlist. Strict Komar "Best Winners" floors remain as
``strict_best_winners`` (env ``TRADING_AGENT_STRENGTH_PROFILE=strict``).

Institutional agent floors (price ≥ $20, ADV ≥ 2M, mcap ≥ $2B, etc.) remain
separate in RiskConfig/ScreenerConfig and are applied *in addition* to these
strength gates — not replaced by them.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Dict, List


@dataclass(frozen=True)
class BestWinnersParams:
    """Growth & momentum strength screen (TradingView-oriented)."""

    name: str = "best_winners"
    source: str = (
        "Julian Komar TradingView growth/momentum screener "
        "(ADR%, 52w low distance, EMA 8/21, 3m performance, dollar volume); "
        "agent default softens ADR/52w/EMA for large-cap regimes"
    )
    market: str = "US"
    # Komar video often uses a soft $1 floor on TV; agent still enforces institutional price floor separately.
    min_price: float = 1.0
    # Softened defaults (was 4.5 / 70% / dual-EMA hard) — see STRICT_BEST_WINNERS
    min_adr_pct: float = 2.5
    adr_lookback: int = 20
    min_pct_above_52w_low: float = 35.0
    ema_fast: int = 8
    ema_slow: int = 21
    require_price_above_ema_fast: bool = True
    require_price_above_ema_slow: bool = False  # dual-EMA was too strict for large caps
    min_performance_3m_pct: float = 0.0  # 3-month performance > 0%
    performance_lookback_bars: int = 63  # ~3 months of trading days
    # price × avg 30d volume ≥ $10M
    min_dollar_volume_avg_30d: float = 10_000_000.0
    avg_volume_lookback: int = 30
    # price × prior-day volume ≥ $5M
    min_dollar_volume_prior_day: float = 5_000_000.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Classic Komar Best Winners floors (optional strict profile)
STRICT_BEST_WINNERS = BestWinnersParams(
    name="strict_best_winners",
    source=(
        "Julian Komar Best Winners strict floors "
        "(ADR%≥4.5, 52w≥70%, price above EMA8 and EMA21)"
    ),
    min_adr_pct=4.5,
    min_pct_above_52w_low=70.0,
    require_price_above_ema_fast=True,
    require_price_above_ema_slow=True,
)

# Explicit soft profile (same as dataclass defaults; named for docs/env)
SOFT_BEST_WINNERS = BestWinnersParams(
    name="soft_best_winners",
    source=(
        "Softened strength gates for large-cap / quieter regimes "
        "(ADR%≥2.5, 52w≥35%, price above EMA8 only)"
    ),
    min_adr_pct=2.5,
    min_pct_above_52w_low=35.0,
    require_price_above_ema_fast=True,
    require_price_above_ema_slow=False,
)


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

    best_winners: BestWinnersParams = field(default_factory=lambda: SOFT_BEST_WINNERS)
    pre_market: PreMarketParams = field(default_factory=PreMarketParams)
    profile_name: str = "soft"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile": self.profile_name,
            "best_winners": self.best_winners.to_dict(),
            "pre_market": self.pre_market.to_dict(),
            "notes": {
                "institutional_floors": (
                    "RiskConfig/ScreenerConfig still enforce price≥$20, ADV≥2M, "
                    "RVOL≥2, mcap≥$2B, options floors — combined with strength gates."
                ),
                "usage": (
                    "Default soft ADR/52w/EMA; set TRADING_AGENT_STRENGTH_PROFILE="
                    "strict|soft or env overrides TRADING_AGENT_MIN_ADR_PCT etc."
                ),
                "strict_best_winners": STRICT_BEST_WINNERS.to_dict(),
            },
        }

    def list_profiles(self) -> List[str]:
        return ["soft", "soft_best_winners", "strict", "strict_best_winners", "pre_market"]


def resolve_strength_profile(name: str | None = None) -> BestWinnersParams:
    """Resolve strength profile from name or env (default soft)."""
    raw = (name or os.getenv("TRADING_AGENT_STRENGTH_PROFILE", "soft") or "soft").strip().lower()
    if raw in ("strict", "strict_best_winners", "komar", "best_winners_strict", "classic"):
        base = STRICT_BEST_WINNERS
        profile = "strict"
    else:
        base = SOFT_BEST_WINNERS
        profile = "soft"

    # Optional numeric env overrides (apply on top of selected profile)
    overrides: Dict[str, Any] = {}
    adr = os.getenv("TRADING_AGENT_MIN_ADR_PCT", "").strip()
    if adr:
        try:
            overrides["min_adr_pct"] = float(adr)
        except ValueError:
            pass
    p52 = os.getenv("TRADING_AGENT_MIN_PCT_ABOVE_52W_LOW", "").strip()
    if p52:
        try:
            overrides["min_pct_above_52w_low"] = float(p52)
        except ValueError:
            pass
    ema_mode = os.getenv("TRADING_AGENT_STRENGTH_EMA_MODE", "").strip().lower()
    if ema_mode in ("both", "dual", "strict"):
        overrides["require_price_above_ema_fast"] = True
        overrides["require_price_above_ema_slow"] = True
    elif ema_mode in ("fast", "ema8", "soft"):
        overrides["require_price_above_ema_fast"] = True
        overrides["require_price_above_ema_slow"] = False
    elif ema_mode in ("none", "off"):
        overrides["require_price_above_ema_fast"] = False
        overrides["require_price_above_ema_slow"] = False

    if overrides:
        base = replace(base, **overrides)
    # keep name marker for debugging
    return replace(base, name=f"{profile}_best_winners" if not overrides else base.name)


DEFAULT_SCREENER_PARAMS = ScreenerParameterSets(
    best_winners=SOFT_BEST_WINNERS,
    profile_name="soft",
)


def get_screener_params(profile: str | None = None) -> ScreenerParameterSets:
    """Return parameter sets with live-resolved strength profile (soft by default)."""
    bw = resolve_strength_profile(profile)
    pname = "strict" if bw.min_adr_pct >= 4.5 and bw.min_pct_above_52w_low >= 70 else "soft"
    # Prefer explicit profile label when env/name set
    env = (profile or os.getenv("TRADING_AGENT_STRENGTH_PROFILE", "soft") or "soft").strip().lower()
    if env in ("strict", "strict_best_winners", "komar", "best_winners_strict", "classic"):
        pname = "strict"
    elif env in ("soft", "soft_best_winners", "default", ""):
        pname = "soft"
    return ScreenerParameterSets(best_winners=bw, profile_name=pname)
