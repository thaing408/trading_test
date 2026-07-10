"""Synthesize overnight markets, economic calendar, and news into actionable context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from trading_agent.models import (
    EconomicCalendar,
    MarketSnapshot,
    NewsCatalysts,
    NewsItem,
    ScreenerCandidate,
)

HIGH_IMPACT_KEYWORDS = (
    "cpi", "ppi", "fomc", "employment", "nonfarm", "gdp", "fed", "powell",
    "treasury auction", "jobless",
)

CATALYST_BOOST = {
    "earnings": 3.0,
    "analyst": 2.0,
    "contract": 2.0,
    "ma": 2.5,
    "insider": 1.5,
    "sec_filing": 1.0,
}

# Prefer institutional catalysts over generic ETF/market wrap headlines in bias text.
_CATALYST_PRIORITY = {
    "earnings": 0,
    "analyst": 1,
    "contract": 2,
    "ma": 3,
    "insider": 4,
    "sec_filing": 5,
    "general": 9,
}

# Live desk used to inject "fixture-fallback" Jobless Claims / fake NVDA headlines — never trust those.
# Explicit source "fixture" is only for AgentConfig.fixture_mode offline tests.
_UNTRUSTED_CATALYST_SOURCES = frozenset({"fixture-fallback", "unavailable", ""})


def _is_real_catalyst_source(source: str) -> bool:
    """True for live APIs (fmp, yfinance), fixture_mode, or unit-test sources — not silent fallbacks."""
    return (source or "").strip().lower() not in _UNTRUSTED_CATALYST_SOURCES


@dataclass
class MarketContext:
    bias: str
    environment_score: float
    signals: List[str] = field(default_factory=list)
    high_impact_events: List[str] = field(default_factory=list)
    calendar_summary: str = ""
    news_highlights: List[str] = field(default_factory=list)
    catalyst_symbols: Dict[str, List[str]] = field(default_factory=dict)
    overnight_summary: Dict[str, str] = field(default_factory=dict)


def _avg_change(group: Dict[str, dict]) -> float:
    changes = [v.get("change_pct", 0) for v in group.values() if v]
    return sum(changes) / len(changes) if changes else 0.0


def _apply_futures(snapshot: MarketSnapshot, score: float, signals: List[str]) -> float:
    for name, data in snapshot.futures.items():
        chg = data.get("change_pct", 0)
        if chg > 0.3:
            score += 3
            if name == "ES":
                signals.append(f"{name} futures +{chg:.2f}%")
        elif chg < -0.3:
            score -= 3
            if name == "ES":
                signals.append(f"{name} futures {chg:.2f}%")
    return score


def _apply_international(snapshot: MarketSnapshot, score: float, signals: List[str]) -> float:
    avg = _avg_change(snapshot.international)
    if avg > 0.2:
        score += 6
        signals.append(f"International markets firm (avg {avg:+.2f}%)")
    elif avg < -0.2:
        score -= 6
        signals.append(f"International markets weak (avg {avg:+.2f}%)")
    return score


def _apply_bonds(snapshot: MarketSnapshot, score: float, signals: List[str]) -> float:
    tlt = snapshot.bonds.get("TLT", {})
    chg = tlt.get("change_pct", 0)
    if chg > 0.3:
        score -= 4
        signals.append(f"Bond bid (TLT {chg:+.2f}%) — flight-to-quality")
    elif chg < -0.3:
        score += 3
        signals.append(f"Bonds sold off (TLT {chg:+.2f}%) — risk appetite")
    return score


def _apply_dxy(snapshot: MarketSnapshot, score: float, signals: List[str]) -> float:
    dxy = snapshot.dollar_index.get("DXY", {})
    chg = dxy.get("change_pct", 0)
    if chg > 0.2:
        score -= 3
        signals.append(f"U.S. Dollar firm (DXY {chg:+.2f}%) — headwind for risk assets")
    elif chg < -0.2:
        score += 3
        signals.append(f"U.S. Dollar soft (DXY {chg:+.2f}%) — tailwind for equities")
    return score


def _apply_vix(snapshot: MarketSnapshot, score: float, signals: List[str]) -> float:
    vix = snapshot.vix.get("VIX", {})
    level = vix.get("last", 20)
    chg = vix.get("change_pct", 0)
    if level and level < 18:
        score += 5
        signals.append(f"VIX subdued at {level:.1f}")
    elif level and level > 25:
        score -= 10
        signals.append(f"Elevated VIX at {level:.1f}")
    if chg > 5:
        score -= 4
        signals.append(f"VIX rising {chg:+.1f}%")
    elif chg < -5:
        score += 3
    return score


def _apply_commodities(snapshot: MarketSnapshot, score: float, signals: List[str]) -> float:
    gold = snapshot.commodities.get("GOLD", {})
    oil = snapshot.commodities.get("OIL", {})
    gold_chg = gold.get("change_pct", 0)
    oil_chg = oil.get("change_pct", 0)
    if gold_chg > 0.5:
        score -= 2
        signals.append(f"Gold firm ({gold_chg:+.2f}%) — hedging demand")
    if oil_chg > 0.5:
        score += 2
        signals.append(f"Oil higher ({oil_chg:+.2f}%) — growth/inflation signal")
    elif oil_chg < -0.5:
        score -= 2
        signals.append(f"Oil weaker ({oil_chg:+.2f}%) — demand concern")
    return score


def _apply_crypto(snapshot: MarketSnapshot, score: float, signals: List[str]) -> float:
    avg = _avg_change(snapshot.crypto)
    if avg > 0.5:
        score += 4
        signals.append(f"Crypto risk-on (avg {avg:+.2f}%)")
    elif avg < -0.5:
        score -= 4
        signals.append(f"Crypto risk-off (avg {avg:+.2f}%)")
    return score


def _apply_sectors(snapshot: MarketSnapshot, signals: List[str]) -> None:
    sectors = snapshot.sector_rotation
    if not sectors:
        return
    leaders = sorted(sectors.items(), key=lambda x: x[1].get("change_pct", 0), reverse=True)
    laggards = sorted(sectors.items(), key=lambda x: x[1].get("change_pct", 0))
    if leaders:
        signals.append(f"Sector leader: {leaders[0][0]} ({leaders[0][1].get('change_pct', 0):+.2f}%)")
    if laggards:
        signals.append(f"Sector laggard: {laggards[0][0]} ({laggards[0][1].get('change_pct', 0):+.2f}%)")


def _calendar_impact(calendar: EconomicCalendar) -> Tuple[float, List[str], str]:
    """Score + high-impact list only for real calendar sources (not fixture fill)."""
    if not _is_real_catalyst_source(calendar.source):
        err = "; ".join(calendar.errors[:1]) if calendar.errors else "no live calendar"
        return 0.0, [], f"Calendar unavailable — {err}"

    adjustment = 0.0
    high_impact: List[str] = []
    for event in calendar.events:
        lower = event.event.lower()
        is_high = event.impact.lower() == "high" or any(k in lower for k in HIGH_IMPACT_KEYWORDS)
        if is_high:
            high_impact.append(f"{event.time}: {event.event}")
            adjustment -= 3
    summary = "No major US macro events today"
    if high_impact:
        summary = f"{len(high_impact)} high-impact event(s) today — reduce size / widen stops"
    elif calendar.events:
        summary = f"{len(calendar.events)} scheduled event(s); no high-impact releases flagged"
    return adjustment, high_impact, summary


def _news_synthesis(news: NewsCatalysts) -> Tuple[Dict[str, List[str]], List[str], float]:
    """Catalysts only when source is live (or explicit test). Fixture headlines never enter bias."""
    if not _is_real_catalyst_source(news.source):
        return {}, [], 0.0

    catalyst_symbols: Dict[str, List[str]] = {}
    highlights: List[str] = []
    score_adj = 0.0

    for item in news.items:
        catalyst_symbols.setdefault(item.symbol, []).append(item.headline)
        if item.category in ("earnings", "analyst", "contract", "ma"):
            score_adj += 0.5

    ranked = sorted(
        news.items,
        key=lambda item: (_CATALYST_PRIORITY.get(item.category, 8), item.symbol),
    )
    for item in ranked[:5]:
        highlights.append(f"[{item.symbol}] {item.headline} ({item.category})")

    return catalyst_symbols, highlights, min(score_adj, 5.0)


def synthesize_market_context(
    market: MarketSnapshot,
    calendar: EconomicCalendar,
    news: NewsCatalysts,
) -> MarketContext:
    score = 50.0
    signals: List[str] = []

    score = _apply_futures(market, score, signals)
    score = _apply_international(market, score, signals)
    score = _apply_bonds(market, score, signals)
    score = _apply_dxy(market, score, signals)
    score = _apply_vix(market, score, signals)
    score = _apply_commodities(market, score, signals)
    score = _apply_crypto(market, score, signals)
    _apply_sectors(market, signals)

    cal_adj, high_impact, cal_summary = _calendar_impact(calendar)
    score += cal_adj

    catalyst_symbols, news_highlights, news_adj = _news_synthesis(news)
    score += news_adj

    score = round(min(100.0, max(0.0, score)), 1)

    if score >= 58:
        bias = "Bullish — risk-on pre-market conditions favor selective long premium or bullish spreads"
    elif score <= 42:
        bias = "Bearish — defensive positioning favored; favor hedges or cash-secured strategies"
    else:
        bias = "Neutral — mixed overnight signals; favor defined-risk premium strategies"

    # Only append calendar/catalyst when from real sources (never fixture Jobless Claims / fake NVDA print)
    if high_impact and _is_real_catalyst_source(calendar.source):
        bias += f"; calendar risk: {high_impact[0]}"
    if news_highlights and _is_real_catalyst_source(news.source):
        bias += f"; active catalyst: {news_highlights[0]}"

    if signals:
        bias += f" ({'; '.join(signals[:4])})"

    provenance: list[str] = []
    if market.source == "yfinance":
        provenance.append("sentiment: live yfinance")
    elif market.source == "fixture":
        provenance.append("sentiment: fixture")
    if _is_real_catalyst_source(calendar.source):
        provenance.append(f"calendar: {calendar.source}")
    elif calendar.source == "unavailable":
        provenance.append("calendar: omitted (no live feed)")
    if _is_real_catalyst_source(news.source):
        provenance.append(f"catalysts: {news.source}")
    elif news.source == "unavailable":
        provenance.append("catalysts: omitted (no live headlines)")
    if provenance:
        bias += f" [data: {', '.join(provenance)}]"

    overnight = {
        "futures": f"ES {market.futures.get('ES', {}).get('change_pct', 0):+.2f}%",
        "international": f"avg {_avg_change(market.international):+.2f}%",
        "bonds": f"TLT {market.bonds.get('TLT', {}).get('change_pct', 0):+.2f}%",
        "dxy": f"DXY {market.dollar_index.get('DXY', {}).get('change_pct', 0):+.2f}%",
        "commodities": f"Gold {market.commodities.get('GOLD', {}).get('change_pct', 0):+.2f}%, Oil {market.commodities.get('OIL', {}).get('change_pct', 0):+.2f}%",
        "crypto": f"avg {_avg_change(market.crypto):+.2f}%",
    }

    return MarketContext(
        bias=bias,
        environment_score=score,
        signals=signals,
        high_impact_events=high_impact,
        calendar_summary=cal_summary,
        news_highlights=news_highlights,
        catalyst_symbols=catalyst_symbols,
        overnight_summary=overnight,
    )


def build_watchlist(
    candidates: List[ScreenerCandidate],
    context: MarketContext,
    limit: int = 10,
) -> List[str]:
    def rank_key(c: ScreenerCandidate) -> float:
        catalyst_boost = sum(
            CATALYST_BOOST.get(_infer_category(headline), 1.0)
            for headline in context.catalyst_symbols.get(c.symbol, [])
        )
        return c.relative_volume * 10 + catalyst_boost

    ranked = sorted(candidates, key=rank_key, reverse=True)
    return [c.symbol for c in ranked[:limit]]


def _infer_category(headline: str) -> str:
    lower = headline.lower()
    if "earnings" in lower or "eps" in lower:
        return "earnings"
    if "upgrade" in lower or "downgrade" in lower:
        return "analyst"
    if "contract" in lower or "award" in lower:
        return "contract"
    if "merger" in lower or "acquisition" in lower:
        return "ma"
    return "general"