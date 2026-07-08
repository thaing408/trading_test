"""Refine confidence scoring from historical results without violating risk rules."""

from __future__ import annotations

from collections import defaultdict
from typing import List

from trading_agent.performance.config import PerformanceConfig
from trading_agent.performance.models import CompletedTrade, ConfidenceRefinement


def refine_confidence(
    history: List[CompletedTrade],
    config: PerformanceConfig,
) -> ConfidenceRefinement:
    notes: list[str] = []
    if len(history) < config.min_trades_for_refinement:
        notes.append(
            f"Insufficient history ({len(history)} trades) for refinement; "
            f"need {config.min_trades_for_refinement}"
        )
        return ConfidenceRefinement(
            strategy_adjustments={},
            sector_adjustments={},
            regime_adjustments={},
            notes=notes,
        )

    def _adjustments(group_key) -> dict[str, float]:
        groups: dict[str, list[float]] = defaultdict(list)
        for t in history:
            key = group_key(t)
            if key:
                groups[key].append(t.profit_loss)
        result = {}
        for key, pls in groups.items():
            if len(pls) < 2:
                continue
            avg = sum(pls) / len(pls)
            adj = max(
                -config.max_confidence_adjustment,
                min(config.max_confidence_adjustment, avg / 50.0),
            )
            result[key] = round(adj, 1)
        return result

    strategy_adj = _adjustments(lambda t: t.strategy)
    sector_adj = _adjustments(lambda t: t.sector)
    regime_adj = _adjustments(lambda t: t.market_regime)

    notes.append(
        "Adjustments bounded to ±{:.0f} pts; risk management rules remain unchanged".format(
            config.max_confidence_adjustment
        )
    )
    if strategy_adj:
        best = max(strategy_adj, key=strategy_adj.get)
        notes.append(f"Boost confidence for {best} by +{strategy_adj[best]:.1f} based on historical edge")
    if regime_adj:
        weak = min(regime_adj, key=regime_adj.get)
        if regime_adj[weak] < 0:
            notes.append(f"Reduce confidence in {weak} regime by {regime_adj[weak]:.1f}")

    return ConfidenceRefinement(
        strategy_adjustments=strategy_adj,
        sector_adjustments=sector_adj,
        regime_adjustments=regime_adj,
        notes=notes,
    )