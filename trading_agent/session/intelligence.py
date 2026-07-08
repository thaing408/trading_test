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
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)


def run_intelligence_pass(config: AgentConfig) -> IntelligenceBrief:
    """Collect overnight market intelligence without technical ranking."""
    from datetime import datetime, timezone

    market = collect_market_snapshot(config)
    calendar = collect_economic_calendar(config)
    news = collect_news_catalysts(config, config.screener.symbols)
    context = synthesize_market_context(market, calendar, news)

    errors: List[str] = []
    errors.extend(market.errors)
    errors.extend(calendar.errors)
    errors.extend(news.errors)

    return IntelligenceBrief(
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        bias=context.bias,
        environment_score=context.environment_score,
        overnight_summary=context.overnight_summary,
        market_signals=context.signals,
        calendar_summary=context.calendar_summary,
        high_impact_events=context.high_impact_events,
        news_highlights=context.news_highlights,
        catalyst_symbols=list(context.catalyst_symbols.keys()),
        errors=errors,
        metadata={
            "market_source": market.source,
            "calendar_source": calendar.source,
            "news_source": news.source,
        },
    )