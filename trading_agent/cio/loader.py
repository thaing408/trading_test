"""Load and synthesize inputs from Phases 1–3."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

from trading_agent.cio.models import PhaseContext, TradeCandidate
from trading_agent.config import AgentConfig
from trading_agent.intraday.config import IntradayConfig
from trading_agent.performance.config import PerformanceConfig

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_from_fixture(path: str | None) -> Tuple[List[TradeCandidate], PhaseContext]:
    file_path = Path(path) if path else FIXTURE_DIR / "cio_inputs.json"
    data = _load_json(file_path)
    candidates = [TradeCandidate(**c) for c in data.get("candidates", [])]
    ctx_data = data.get("context", {})
    context = PhaseContext(
        overall_market_bias=ctx_data.get("overall_market_bias", ""),
        market_environment_score=ctx_data.get("market_environment_score", 50.0),
        market_regime=ctx_data.get("market_regime", "neutral"),
        stay_in_cash=ctx_data.get("stay_in_cash", False),
        intraday_flags=ctx_data.get("intraday_flags", {}),
        strategy_refinement=ctx_data.get("strategy_refinement", {}),
        sector_refinement=ctx_data.get("sector_refinement", {}),
        weakest_strategies=ctx_data.get("weakest_strategies", []),
        performance_notes=ctx_data.get("performance_notes", []),
    )
    return candidates, context


def load_from_pipelines() -> Tuple[List[TradeCandidate], PhaseContext]:
    """Synthesize CIO inputs by running Phase 1–3 pipelines in fixture mode."""
    from trading_agent.intraday.pipeline import run_intraday_pipeline
    from trading_agent.performance.pipeline import run_performance_pipeline
    from trading_agent.pipeline import run_pipeline

    plan = run_pipeline(AgentConfig(fixture_mode=True, use_live_data=False))
    intraday = run_intraday_pipeline(IntradayConfig(fixture_mode=True, use_live_data=False))
    performance = run_performance_pipeline(PerformanceConfig(fixture_mode=True))

    candidates: List[TradeCandidate] = []
    for opp in plan.ranked_opportunities:
        candidates.append(
            TradeCandidate(
                symbol=opp.symbol,
                direction="Bullish" if "Call" in opp.strategy or "bullish" in opp.strategy.lower() else "Neutral",
                strategy=opp.strategy,
                entry_price=opp.entry_price,
                strike_prices=opp.strike_prices,
                expiration=opp.expiration,
                profit_target=opp.profit_target,
                stop_loss=opp.stop_loss,
                maximum_risk=opp.maximum_risk,
                maximum_reward=opp.maximum_reward,
                probability_of_success=opp.probability_of_success,
                confidence_score=opp.confidence_score,
                primary_catalyst="; ".join(opp.supporting_reasons[:1]) if opp.supporting_reasons else "technical",
                catalyst_type="technical",
                technical_summary=f"Trend {opp.technical.trend}, RSI {opp.technical.rsi}",
                technical_confirmations=[
                    f"trend:{opp.technical.trend}",
                    f"macd:{opp.technical.macd_signal}",
                    f"vwap:{opp.technical.vwap_relation}",
                    f"ma:{opp.technical.ma_alignment}",
                ],
                options_summary=f"IV rank {opp.options.iv_rank}, liquidity {opp.options.liquidity_score}",
                open_interest=1000,
                daily_options_volume=5000,
                bid_ask_spread_pct=2.0,
                iv_rank=opp.options.iv_rank,
                expected_move_pct=opp.options.expected_move_pct,
                probability_of_profit=opp.options.probability_of_profit,
                liquidity_score=opp.options.liquidity_score,
                sector="Unknown",
                phase1_rank=opp.rank,
            )
        )

    intraday_flags = {r.symbol: r.action for r in intraday.recommendations}
    context = PhaseContext(
        overall_market_bias=plan.overall_market_bias,
        market_environment_score=plan.market_environment_score,
        market_regime=plan.research_summary.get("market_regime", "neutral")
        if isinstance(plan.research_summary, dict)
        else "neutral",
        stay_in_cash=plan.stay_in_cash,
        intraday_flags=intraday_flags,
        strategy_refinement=performance.refinement.strategy_adjustments,
        sector_refinement=performance.refinement.sector_adjustments,
        weakest_strategies=performance.patterns.weakest_strategies,
        performance_notes=performance.lessons_learned[:3],
    )
    return candidates, context


def load_cio_inputs(fixture_mode: bool, inputs_file: str | None) -> Tuple[List[TradeCandidate], PhaseContext]:
    if fixture_mode:
        return load_from_fixture(inputs_file)
    try:
        candidates, context = load_from_pipelines()
        if candidates:
            return candidates, context
    except Exception:
        pass
    return load_from_fixture(inputs_file)