"""Load Daily Trading Plan context and open positions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from trading_agent.intraday.models import OpenPosition

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def load_positions(path: str | None, fixture_mode: bool) -> List[OpenPosition]:
    if path:
        with Path(path).open(encoding="utf-8") as handle:
            data = json.load(handle)
        return [OpenPosition(**p) for p in data.get("positions", [])]
    if fixture_mode:
        with (FIXTURE_DIR / "open_positions.json").open(encoding="utf-8") as handle:
            data = json.load(handle)
        return [OpenPosition(**p) for p in data.get("positions", [])]
    return []


def load_plan_context(path: str | None, fixture_mode: bool) -> dict:
    if path:
        with Path(path).open(encoding="utf-8") as handle:
            return json.load(handle)
    if fixture_mode:
        with (FIXTURE_DIR / "daily_plan_context.json").open(encoding="utf-8") as handle:
            return json.load(handle)
    return {
        "overall_market_bias": "Neutral",
        "market_environment_score": 50.0,
        "market_regime": "neutral",
        "top_watchlist": [],
        "news_highlights": [],
        "high_impact_events": [],
        "stay_in_cash": True,
    }