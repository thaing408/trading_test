"""Synthesize overnight markets, economic calendar, and news into actionable context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from trading_agent.models import (
    EconomicCalendar,
    MarketSnapshot,
    NewsCatalysts,
    ScreenerCandidate,
)

# High-impact macro types aligned to institutional calendar coverage.
HIGH_IMPACT_KEYWORDS = (
    "cpi",
    "ppi",
    "pce",
    "fomc",
    "employment",
    "nonfarm",
    "nfp",
    "unemployment",
    "jobless",
    "payroll",
    "gdp",
    "fed",
    "powell",
    "yellen",
    "treasury auction",
    "auction",
    "rate decision",
    "interest rate",
    "ism",
    "retail sales",
    "housing starts",
)

CATALYST_BOOST = {
    "earnings": 3.0,
    "analyst": 2.0,
    "contract": 2.0,
    "ma": 2.5,
    "insider": 1.5,
    "sec_filing": 1.0,
    "ai": 2.0,
    "semiconductor": 2.0,
    "geopolitical": 1.5,
}

_CATALYST_PRIORITY = {
    "earnings": 0,
    "analyst": 1,
    "contract": 2,
    "ma": 3,
    "ai": 3,
    "semiconductor": 3,
    "insider": 4,
    "sec_filing": 5,
    "geopolitical": 6,
    "general": 9,
}

# Live desk used to inject "fixture-fallback" Jobless Claims / fake NVDA headlines — never trust those.
# Explicit source "fixture" is only for AgentConfig.fixture_mode offline tests.
_UNTRUSTED_CATALYST_SOURCES = frozenset({"fixture-fallback", "unavailable", ""})

NAMED_ETFS = ("SPY", "QQQ", "IWM", "DIA", "XLK", "SMH", "SOXX", "XLF", "XLE", "XBI")

ASIA_KEYS = ("NIKKEI", "HSI", "SHANGHAI", "ASX", "KOSPI")
EUROPE_KEYS = ("FTSE", "DAX", "CAC", "STOXX50")


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
    # Institutional conclusion fields (intelligence brief; not trade tickets)
    outlook: str = "Neutral"  # Bullish | Bearish | Neutral
    market_posture: str = ""
    sector_ranking: List[str] = field(default_factory=list)
    etf_snapshot: List[str] = field(default_factory=list)
    breadth_notes: List[str] = field(default_factory=list)
    top_opportunities: List[str] = field(default_factory=list)
    major_risks: List[str] = field(default_factory=list)
    expected_drivers: List[str] = field(default_factory=list)
    unavailable_series: Dict[str, str] = field(default_factory=dict)
    vix_term_note: str = ""
    yield_curve_note: str = ""


def _finite_change(value: object) -> float | None:
    """Return float change_pct only when finite; drop NaN/inf."""
    try:
        import math

        num = float(value)  # type: ignore[arg-type]
        if not math.isfinite(num):
            return None
        return num
    except (TypeError, ValueError):
        return None


def _avg_change(group: Dict[str, dict]) -> float | None:
    """Average change_pct over finite values; None when group empty or all non-finite."""
    changes: List[float] = []
    for v in group.values():
        if not v:
            continue
        chg = _finite_change(v.get("change_pct"))
        if chg is not None:
            changes.append(chg)
    if not changes:
        return None
    return sum(changes) / len(changes)


def _subset_avg(group: Dict[str, dict], keys: Tuple[str, ...]) -> float | None:
    vals: List[float] = []
    for k in keys:
        if k not in group or not group[k]:
            continue
        chg = _finite_change(group[k].get("change_pct"))
        if chg is not None:
            vals.append(chg)
    if not vals:
        return None
    return sum(vals) / len(vals)


def _fmt_chg(value: object, default: str = "unavailable") -> str:
    chg = _finite_change(value)
    if chg is None:
        return default
    return f"{chg:+.2f}%"


def _apply_futures(snapshot: MarketSnapshot, score: float, signals: List[str]) -> float:
    for name, data in snapshot.futures.items():
        chg = _finite_change(data.get("change_pct"))
        if chg is None:
            continue
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
    asia = _subset_avg(snapshot.international, ASIA_KEYS)
    europe = _subset_avg(snapshot.international, EUROPE_KEYS)
    avg = _avg_change(snapshot.international)
    if asia is not None:
        if asia > 0.2:
            score += 3
            signals.append(f"Asia firm (avg {asia:+.2f}%)")
        elif asia < -0.2:
            score -= 3
            signals.append(f"Asia weak (avg {asia:+.2f}%)")
    if europe is not None:
        if europe > 0.2:
            score += 3
            signals.append(f"Europe firm (avg {europe:+.2f}%)")
        elif europe < -0.2:
            score -= 3
            signals.append(f"Europe weak (avg {europe:+.2f}%)")
    if asia is None and europe is None and avg is not None:
        if avg > 0.2:
            score += 6
            signals.append(f"International markets firm (avg {avg:+.2f}%)")
        elif avg < -0.2:
            score -= 6
            signals.append(f"International markets weak (avg {avg:+.2f}%)")
    return score


def _apply_bonds(snapshot: MarketSnapshot, score: float, signals: List[str]) -> float:
    tlt = snapshot.bonds.get("TLT", {})
    chg = _finite_change(tlt.get("change_pct"))
    if chg is None:
        return score
    if chg > 0.3:
        score -= 4
        signals.append(f"Bond bid (TLT {chg:+.2f}%) — flight-to-quality")
    elif chg < -0.3:
        score += 3
        signals.append(f"Bonds sold off (TLT {chg:+.2f}%) — risk appetite")
    return score


def _apply_dxy(snapshot: MarketSnapshot, score: float, signals: List[str]) -> float:
    dxy = snapshot.dollar_index.get("DXY", {})
    chg = _finite_change(dxy.get("change_pct"))
    if chg is None:
        return score
    if chg > 0.2:
        score -= 3
        signals.append(f"U.S. Dollar firm (DXY {chg:+.2f}%) — headwind for risk assets")
    elif chg < -0.2:
        score += 3
        signals.append(f"U.S. Dollar soft (DXY {chg:+.2f}%) — tailwind for equities")
    return score


def _apply_vix(snapshot: MarketSnapshot, score: float, signals: List[str]) -> Tuple[float, str]:
    vix = snapshot.vix.get("VIX", {})
    vix3m = snapshot.vix.get("VIX3M", {})
    level = _finite_change(vix.get("last", 20))
    chg = _finite_change(vix.get("change_pct"))
    term_note = ""
    if level is not None and level < 18:
        score += 5
        signals.append(f"VIX subdued at {level:.1f}")
    elif level is not None and level > 25:
        score -= 10
        signals.append(f"Elevated VIX at {level:.1f}")
    if chg is not None and chg > 5:
        score -= 4
        signals.append(f"VIX rising {chg:+.1f}%")
    elif chg is not None and chg < -5:
        score += 3
    spot = _finite_change(vix.get("last"))
    mid = _finite_change(vix3m.get("last"))
    if spot is not None and mid is not None and mid > 0:
        if spot < mid:
            term_note = f"VIX term structure contango (spot {spot:.1f} < VIX3M {mid:.1f})"
            score += 1
        elif spot > mid * 1.02:
            term_note = f"VIX term structure inversion risk (spot {spot:.1f} > VIX3M {mid:.1f})"
            score -= 3
            signals.append("VIX term structure inverted/flat — stress signal")
        else:
            term_note = f"VIX term structure near flat (spot {spot:.1f} vs VIX3M {mid:.1f})"
    elif "VIX" in snapshot.vix and "VIX3M" not in snapshot.vix:
        term_note = "VIX3M unavailable — term structure not assessed"
    return score, term_note


def _apply_commodities(snapshot: MarketSnapshot, score: float, signals: List[str]) -> float:
    gold_chg = _finite_change(snapshot.commodities.get("GOLD", {}).get("change_pct"))
    oil_chg = _finite_change(snapshot.commodities.get("OIL", {}).get("change_pct"))
    copper_chg = _finite_change(snapshot.commodities.get("COPPER", {}).get("change_pct"))
    ng_chg = _finite_change(snapshot.commodities.get("NATGAS", {}).get("change_pct"))
    if gold_chg is not None and gold_chg > 0.5:
        score -= 2
        signals.append(f"Gold firm ({gold_chg:+.2f}%) — hedging demand")
    if oil_chg is not None and oil_chg > 0.5:
        score += 2
        signals.append(f"Oil higher ({oil_chg:+.2f}%) — growth/inflation signal")
    elif oil_chg is not None and oil_chg < -0.5:
        score -= 2
        signals.append(f"Oil weaker ({oil_chg:+.2f}%) — demand concern")
    if copper_chg is not None and copper_chg > 0.4:
        score += 2
        signals.append(f"Copper firm ({copper_chg:+.2f}%) — industrial demand")
    elif copper_chg is not None and copper_chg < -0.4:
        score -= 2
        signals.append(f"Copper soft ({copper_chg:+.2f}%) — growth concern")
    if ng_chg is not None and abs(ng_chg) > 2:
        signals.append(f"Natural gas volatile ({ng_chg:+.2f}%)")
    return score


def _apply_crypto(snapshot: MarketSnapshot, score: float, signals: List[str]) -> float:
    avg = _avg_change(snapshot.crypto)
    if avg is None:
        return score
    if avg > 0.5:
        score += 4
        signals.append(f"Crypto risk-on (avg {avg:+.2f}%)")
    elif avg < -0.5:
        score -= 4
        signals.append(f"Crypto risk-off (avg {avg:+.2f}%)")
    return score


def _apply_yields(snapshot: MarketSnapshot, score: float, signals: List[str]) -> Tuple[float, str]:
    y10 = snapshot.treasury_yields.get("US10Y", {})
    y2 = snapshot.treasury_yields.get("US2Y", {})
    note = ""
    if y10.get("last") is not None and y2.get("last") is not None:
        # ^IRX is discount rate scale ~ percent*10 historically; treat as levels if both present
        level_10 = float(y10["last"])
        level_2 = float(y2["last"])
        # Normalize if IRX looks like discount (e.g. 4.85 vs 48.5)
        if level_2 > 20 and level_10 < 20:
            level_2 = level_2 / 10.0
        spread = level_10 - level_2
        note = f"Yield curve 10Y-2Y approx {spread:+.2f} pts (10Y {level_10:.2f}, 2Y {level_2:.2f})"
        if y10.get("change_pct", 0) > 0.15:
            score -= 1
            signals.append(f"10Y yields rising ({y10.get('change_pct', 0):+.2f}%)")
        elif y10.get("change_pct", 0) < -0.15:
            score += 1
            signals.append(f"10Y yields falling ({y10.get('change_pct', 0):+.2f}%)")
    elif snapshot.unavailable.get("CME_FEDWATCH"):
        note = "Treasury yields sparse; CME FedWatch unavailable"
    return score, note


def _sector_ranking(snapshot: MarketSnapshot) -> List[str]:
    sectors = snapshot.sector_rotation
    if not sectors:
        return []
    scored: List[Tuple[str, float]] = []
    for name, data in sectors.items():
        chg = _finite_change((data or {}).get("change_pct"))
        if chg is None:
            continue
        scored.append((name, chg))
    ordered = sorted(scored, key=lambda x: x[1], reverse=True)
    return [f"{name} ({chg:+.2f}%)" for name, chg in ordered]


def _apply_sectors(snapshot: MarketSnapshot, signals: List[str], score: float) -> float:
    ranking = _sector_ranking(snapshot)
    if not ranking:
        return score
    signals.append(f"Sector leader: {ranking[0]}")
    signals.append(f"Sector laggard: {ranking[-1]}")

    # Risk-on if cyclicals/tech lead defensives
    sectors = snapshot.sector_rotation
    tech = _finite_change(sectors.get("XLK", {}).get("change_pct")) or 0.0
    util = _finite_change(sectors.get("XLU", {}).get("change_pct")) or 0.0
    staples = _finite_change(sectors.get("XLP", {}).get("change_pct")) or 0.0
    energy = _finite_change(sectors.get("XLE", {}).get("change_pct")) or 0.0
    if tech > util and tech > staples and tech > 0.2:
        score += 2
        signals.append("Institutional rotation: risk-on (tech leading defensives)")
    elif util > tech and staples > tech:
        score -= 2
        signals.append("Institutional rotation: defensive (utilities/staples leading)")
    if energy < -0.3 and tech > 0.3:
        signals.append("Energy lagging with tech leadership — growth/risk-on skew")
    return score


def _etf_snapshot(snapshot: MarketSnapshot) -> List[str]:
    lines: List[str] = []
    etfs = snapshot.etfs or {}
    for name in NAMED_ETFS:
        data = etfs.get(name)
        if data:
            chg = _fmt_chg(data.get("change_pct"))
            last = data.get("last", "n/a")
            if _finite_change(last) is None and last != "n/a":
                last = "n/a"
            lines.append(f"{name} {chg} @ {last}")
        else:
            lines.append(f"{name}: unavailable")
    return lines


def _breadth_notes(snapshot: MarketSnapshot) -> List[str]:
    notes: List[str] = []
    breadth = snapshot.breadth or {}
    if not breadth:
        notes.append("Market breadth: unavailable (no internals feed)")
        return notes
    for key, val in breadth.items():
        if isinstance(val, dict):
            status = val.get("status", "unavailable")
            if status == "ok":
                notes.append(f"{key}: {val.get('value', val)}")
            else:
                notes.append(f"{key}: unavailable — {val.get('note', 'no feed')}")
        else:
            notes.append(f"{key}: {val}")
    return notes


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
        # Risk flag only — no position size / stop-loss guidance in Market Intelligence
        summary = (
            f"{len(high_impact)} high-impact event(s) today — "
            "elevated event risk into the open"
        )
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
        if item.category in ("earnings", "analyst", "contract", "ma", "ai", "semiconductor"):
            score_adj += 0.5

    ranked = sorted(
        news.items,
        key=lambda item: (_CATALYST_PRIORITY.get(item.category, 8), item.symbol),
    )
    for item in ranked[:5]:
        highlights.append(f"[{item.symbol}] {item.headline} ({item.category})")

    return catalyst_symbols, highlights, min(score_adj, 5.0)


def _build_conclusions(
    score: float,
    outlook: str,
    signals: List[str],
    high_impact: List[str],
    news_highlights: List[str],
    sector_ranking: List[str],
    etf_lines: List[str],
    snapshot: MarketSnapshot,
    cal_summary: str,
) -> Tuple[List[str], List[str], List[str], str]:
    """Thematic opportunities/risks/drivers/posture — never option trade tickets."""
    opportunities: List[str] = []
    risks: List[str] = []
    drivers: List[str] = []

    if sector_ranking:
        opportunities.append(f"Sector leadership focus: {sector_ranking[0]}")
        if len(sector_ranking) > 1:
            opportunities.append(f"Relative strength continuum: {', '.join(sector_ranking[:3])}")
    smh = next((e for e in etf_lines if e.startswith("SMH ") or e.startswith("SOXX ")), None)
    if smh and "+" in smh:
        opportunities.append(f"Semiconductor complex firm ({smh.split(' @')[0]})")
    crypto_avg = _avg_change(snapshot.crypto)
    if crypto_avg is not None and crypto_avg > 0.5:
        opportunities.append("Overnight crypto risk-on may support high-beta growth tone")
    if score >= 58:
        opportunities.append("Constructive overnight tape supports selective risk engagement (research only)")
    if not opportunities:
        opportunities.append("No clear thematic edge overnight — preserve optionality")

    if high_impact:
        risks.append(f"Macro calendar risk: {high_impact[0]}")
    vix_level = _finite_change(snapshot.vix.get("VIX", {}).get("last"))
    if vix_level is not None and vix_level > 22:
        risks.append(f"Elevated volatility regime (VIX {vix_level:.1f})")
    if sector_ranking:
        risks.append(f"Weak sector exposure: {sector_ranking[-1]}")
    if snapshot.unavailable:
        risks.append(
            "Incomplete internals/FedWatch/MOVE — posture less confident without full tape"
        )
    dxy_chg = _finite_change(snapshot.dollar_index.get("DXY", {}).get("change_pct"))
    if dxy_chg is not None and dxy_chg > 0.25:
        risks.append("Firm USD can pressure risk assets and commodities")
    if not risks:
        risks.append("Standard gap risk into the cash open")

    es = snapshot.futures.get("ES", {})
    es_chg = _fmt_chg((es or {}).get("change_pct"))
    if es:
        drivers.append(f"U.S. index futures (ES {es_chg})")
    if high_impact:
        drivers.append(f"Scheduled macro: {high_impact[0]}")
    elif cal_summary and "unavailable" not in cal_summary.lower():
        drivers.append(cal_summary)
    if news_highlights:
        drivers.append(f"Headline flow: {news_highlights[0]}")
    if sector_ranking:
        drivers.append(f"Sector rotation: leader {sector_ranking[0]}, laggard {sector_ranking[-1]}")
    if not drivers:
        drivers.append("Overnight futures and global equity tone")

    if outlook == "Bullish":
        posture = "Risk-on bias with standard overnight gap discipline — no trade tickets in MI"
    elif outlook == "Bearish":
        posture = "Defensive / elevated cash bias until tape improves — no trade tickets in MI"
    else:
        posture = "Balanced / wait-and-see posture into the open — no trade tickets in MI"

    # Cap lists for Discord brevity
    return opportunities[:5], risks[:5], drivers[:5], posture


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
    score, vix_term_note = _apply_vix(market, score, signals)
    score = _apply_commodities(market, score, signals)
    score = _apply_crypto(market, score, signals)
    score, yield_note = _apply_yields(market, score, signals)
    score = _apply_sectors(market, signals, score)

    cal_adj, high_impact, cal_summary = _calendar_impact(calendar)
    score += cal_adj

    catalyst_symbols, news_highlights, news_adj = _news_synthesis(news)
    score += news_adj

    score = round(min(100.0, max(0.0, score)), 1)

    if score >= 58:
        outlook = "Bullish"
        bias = "Bullish — risk-on pre-market conditions"
    elif score <= 42:
        outlook = "Bearish"
        bias = "Bearish — defensive risk posture overnight"
    else:
        outlook = "Neutral"
        bias = "Neutral — mixed overnight signals"

    # Only append calendar/catalyst when from real sources (never fixture Jobless Claims / fake NVDA print)
    if high_impact and (_is_real_catalyst_source(calendar.source) or calendar.source == "fmp-earnings"):
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
    if _is_real_catalyst_source(calendar.source) or calendar.source == "fmp-earnings":
        provenance.append(f"calendar: {calendar.source}")
    elif calendar.source == "unavailable":
        provenance.append("calendar: omitted (no live feed)")
    if _is_real_catalyst_source(news.source):
        provenance.append(f"catalysts: {news.source}")
    elif news.source == "unavailable":
        provenance.append("catalysts: omitted (no live headlines)")
    if provenance:
        bias += f" [data: {', '.join(provenance)}]"

    asia = _subset_avg(market.international, ASIA_KEYS)
    europe = _subset_avg(market.international, EUROPE_KEYS)
    intl_avg = _avg_change(market.international)
    crypto_avg = _avg_change(market.crypto)
    overnight = {
        "futures": f"ES {_fmt_chg(market.futures.get('ES', {}).get('change_pct'))}",
        "asia": f"avg {asia:+.2f}%" if asia is not None else "unavailable",
        "europe": f"avg {europe:+.2f}%" if europe is not None else "unavailable",
        "international": (
            f"avg {intl_avg:+.2f}%" if intl_avg is not None else "unavailable"
        ),
        "bonds": f"TLT {_fmt_chg(market.bonds.get('TLT', {}).get('change_pct'))}",
        "dxy": f"DXY {_fmt_chg(market.dollar_index.get('DXY', {}).get('change_pct'))}",
        "commodities": (
            f"Gold {_fmt_chg(market.commodities.get('GOLD', {}).get('change_pct'))}, "
            f"Silver {_fmt_chg(market.commodities.get('SILVER', {}).get('change_pct'))}, "
            f"Oil {_fmt_chg(market.commodities.get('OIL', {}).get('change_pct'))}, "
            f"Copper {_fmt_chg(market.commodities.get('COPPER', {}).get('change_pct'))}, "
            f"NG {_fmt_chg(market.commodities.get('NATGAS', {}).get('change_pct'))}"
        ),
        "crypto": (
            f"BTC {_fmt_chg(market.crypto.get('BTC', {}).get('change_pct'))}, "
            f"ETH {_fmt_chg(market.crypto.get('ETH', {}).get('change_pct'))}"
            + (f" (avg {crypto_avg:+.2f}%)" if crypto_avg is not None else "")
        ),
        "vix": (
            f"VIX {market.vix.get('VIX', {}).get('last', 'n/a')} "
            f"({_fmt_chg(market.vix.get('VIX', {}).get('change_pct'), default='n/a')})"
        ),
    }

    ranking = _sector_ranking(market)
    etf_lines = _etf_snapshot(market)
    breadth = _breadth_notes(market)
    opportunities, risks, drivers, posture = _build_conclusions(
        score,
        outlook,
        signals,
        high_impact,
        news_highlights,
        ranking,
        etf_lines,
        market,
        cal_summary,
    )

    unavailable = dict(market.unavailable or {})
    for key, val in (market.breadth or {}).items():
        if isinstance(val, dict) and val.get("status") == "unavailable":
            unavailable.setdefault(key, val.get("note", "unavailable"))

    return MarketContext(
        bias=bias,
        environment_score=score,
        signals=signals,
        high_impact_events=high_impact,
        calendar_summary=cal_summary,
        news_highlights=news_highlights,
        catalyst_symbols=catalyst_symbols,
        overnight_summary=overnight,
        outlook=outlook,
        market_posture=posture,
        sector_ranking=ranking,
        etf_snapshot=etf_lines,
        breadth_notes=breadth,
        top_opportunities=opportunities,
        major_risks=risks,
        expected_drivers=drivers,
        unavailable_series=unavailable,
        vix_term_note=vix_term_note,
        yield_curve_note=yield_note,
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
    if "semiconductor" in lower or "chip" in lower:
        return "semiconductor"
    if "artificial intelligence" in lower or " ai " in f" {lower} ":
        return "ai"
    return "general"
