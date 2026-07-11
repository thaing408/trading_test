"""Market Intelligence pass — collectors and synthesis without ranking."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from trading_agent.collectors import (
    collect_economic_calendar,
    collect_market_snapshot,
    collect_news_catalysts,
)
from trading_agent.config import AgentConfig
from trading_agent.synthesis.market_context import synthesize_market_context


@dataclass
class IntelligenceBrief:
    date: str
    bias: str
    environment_score: float
    overnight_summary: Dict[str, Any]
    market_signals: List[str]
    calendar_summary: str
    high_impact_events: List[str]
    news_highlights: List[str]
    catalyst_symbols: List[str]
    # Institutional conclusion block
    outlook: str = "Neutral"
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
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)


def _benchmark_pa_notes(config: AgentConfig) -> tuple[List[str], List[str]]:
    """Institutional PA / candle context from SPY (and QQQ) for MI risks/opportunities."""
    from trading_agent.analysis.patterns import detect_all_patterns
    from trading_agent.pipeline import _get_ohlcv

    opportunities: List[str] = []
    risks: List[str] = []
    for symbol in ("SPY", "QQQ"):
        bars = _get_ohlcv(symbol, config, interval="1d", period="6mo")
        closes = bars.get("close") or []
        highs = bars.get("high") or []
        lows = bars.get("low") or []
        if len(closes) < 15:
            continue
        report = detect_all_patterns(
            closes,
            highs,
            lows,
            bars.get("volume"),
            opens=bars.get("open"),
        )
        if not report.signals:
            continue
        summary = report.summary()
        for sig in report.signals:
            label = f"{symbol} {sig.name}"
            if sig.bias == "bullish":
                opportunities.append(
                    f"Institutional PA / candle: {label} — {sig.note or sig.bias}"
                )
            elif sig.bias == "bearish":
                risks.append(
                    f"Institutional PA trap risk: {label} — {sig.note or sig.bias}"
                )
            else:
                risks.append(f"Price-action indecision: {label} ({summary})")
    # Deduplicate-ish and cap
    def _uniq(items: List[str], n: int = 3) -> List[str]:
        seen: set[str] = set()
        out: List[str] = []
        for x in items:
            if x not in seen:
                seen.add(x)
                out.append(x)
            if len(out) >= n:
                break
        return out

    return _uniq(opportunities), _uniq(risks)


def run_intelligence_pass(config: AgentConfig) -> IntelligenceBrief:
    """Collect overnight market intelligence without technical ranking or trade tickets."""
    from datetime import datetime, timezone

    market = collect_market_snapshot(config)
    calendar = collect_economic_calendar(config)
    news = collect_news_catalysts(config, config.screener.symbols)
    context = synthesize_market_context(market, calendar, news)

    errors: List[str] = []
    errors.extend(market.errors)
    errors.extend(calendar.errors)
    errors.extend(news.errors)

    pa_ops, pa_risks = _benchmark_pa_notes(config)
    top_opportunities = list(context.top_opportunities)
    major_risks = list(context.major_risks)
    for item in pa_ops:
        if item not in top_opportunities:
            top_opportunities.insert(0, item)
    for item in pa_risks:
        if item not in major_risks:
            major_risks.insert(0, item)
    top_opportunities = top_opportunities[:6]
    major_risks = major_risks[:6]
    signals = list(context.signals)
    if pa_ops or pa_risks:
        signals.append(
            "Institutional PA cheat-sheet scan (stop-hunt/fakeout/QML/RS-flip + candles) on SPY/QQQ"
        )

    return IntelligenceBrief(
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        bias=context.bias,
        environment_score=context.environment_score,
        overnight_summary=context.overnight_summary,
        market_signals=signals,
        calendar_summary=context.calendar_summary,
        high_impact_events=context.high_impact_events,
        news_highlights=context.news_highlights,
        catalyst_symbols=list(context.catalyst_symbols.keys()),
        outlook=context.outlook,
        market_posture=context.market_posture,
        sector_ranking=context.sector_ranking,
        etf_snapshot=context.etf_snapshot,
        breadth_notes=context.breadth_notes,
        top_opportunities=top_opportunities,
        major_risks=major_risks,
        expected_drivers=context.expected_drivers,
        unavailable_series=context.unavailable_series,
        vix_term_note=context.vix_term_note,
        yield_curve_note=context.yield_curve_note,
        errors=errors,
        metadata={
            "market_source": market.source,
            "calendar_source": calendar.source,
            "news_source": news.source,
            "pa_scan": "spy_qqq",
        },
    )
