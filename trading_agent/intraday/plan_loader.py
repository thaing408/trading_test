"""Load Daily Trading Plan context and open positions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from trading_agent.intraday.models import OpenPosition

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def load_positions(path: str | None, fixture_mode: bool) -> List[OpenPosition]:
    """Load open positions: explicit file → fixture → optional brokerage → empty.

    Live path never synthesizes demo positions when brokerage is unconfigured.
    """
    if path:
        with Path(path).open(encoding="utf-8") as handle:
            data = json.load(handle)
        return [OpenPosition(**p) for p in data.get("positions", [])]
    if fixture_mode:
        with (FIXTURE_DIR / "open_positions.json").open(encoding="utf-8") as handle:
            data = json.load(handle)
        return [OpenPosition(**p) for p in data.get("positions", [])]

    # Optional brokerage (Alpaca / Tradier) — fail closed
    try:
        from trading_agent.providers.brokerage import load_broker_positions
        from trading_agent.providers.config import ProviderConfig

        result = load_broker_positions(ProviderConfig.from_env())
        if result.ok and result.positions:
            out: List[OpenPosition] = []
            for row in result.positions:
                symbol = (row.get("symbol") or "").strip()
                if not symbol:
                    continue
                qty = float(row.get("qty") or 0)
                if qty == 0:
                    continue
                entry = float(row.get("avg_entry_price") or row.get("current_price") or 0)
                price = float(row.get("current_price") or entry)
                # Desk OpenPosition is options-oriented; map equity holdings as stock proxy.
                out.append(
                    OpenPosition(
                        symbol=symbol,
                        strategy=str(row.get("broker") or "brokerage"),
                        entry_price=entry,
                        stop_loss=entry * 0.95 if entry else 0.0,
                        profit_target=entry * 1.05 if entry else 0.0,
                        strike_prices=[],
                        expiration="",
                        quantity=max(1, int(abs(qty))),
                        thesis=f"Brokerage position via {row.get('broker') or 'unknown'}",
                        current_price=price,
                    )
                )
            return out
    except Exception:
        pass
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