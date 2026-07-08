"""Persist pre-market plan context for intraday cycles."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from trading_agent.models import DailyTradingPlan


def infer_market_regime(bias: str) -> str:
    lower = bias.lower()
    if "bearish" in lower:
        return "bearish"
    if "bullish" in lower:
        return "bullish"
    return "neutral"


def plan_to_context(plan: DailyTradingPlan) -> dict:
    return {
        "date": plan.date,
        "overall_market_bias": plan.overall_market_bias,
        "market_environment_score": plan.market_environment_score,
        "market_regime": infer_market_regime(plan.overall_market_bias),
        "top_watchlist": plan.top_watchlist,
        "news_highlights": plan.research_summary.get("news_highlights", []),
        "high_impact_events": plan.research_summary.get("high_impact_events", []),
        "stay_in_cash": plan.stay_in_cash,
        "cash_recommendation_reason": plan.cash_recommendation_reason,
        "ranked_symbols": [opp.symbol for opp in plan.ranked_opportunities],
        "ranked_opportunities": [
            {
                "symbol": opp.symbol,
                "strategy": opp.strategy,
                "entry_price": opp.entry_price,
                "confidence_score": opp.confidence_score,
                "probability_of_success": opp.probability_of_success,
                "maximum_risk": opp.maximum_risk,
                "maximum_reward": opp.maximum_reward,
            }
            for opp in plan.ranked_opportunities
        ],
    }


def default_session_dir(trading_date: date, base: Path | None = None) -> Path:
    root = base or Path.home() / ".trading_agent" / "sessions"
    path = root / trading_date.isoformat()
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_plan_context(context: dict, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    out = directory / "daily_plan_context.json"
    with out.open("w", encoding="utf-8") as handle:
        json.dump(context, handle, indent=2)
    return out


def load_saved_plan_context(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)