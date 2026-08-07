"""Load and synthesize inputs from Phases 1–3."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Literal, Tuple

from trading_agent.cio.models import PhaseContext, TradeCandidate
from trading_agent.config import AgentConfig
from trading_agent.intraday.config import IntradayConfig
from trading_agent.models import DailyTradingPlan
from trading_agent.performance.config import PerformanceConfig
from trading_agent.regime import infer_market_regime

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _trade_candidate_from_dict(raw: dict) -> TradeCandidate:
    """Build TradeCandidate ignoring unknown keys (forward/back compat)."""
    import dataclasses

    names = {f.name for f in dataclasses.fields(TradeCandidate)}
    payload = {k: v for k, v in raw.items() if k in names}
    return TradeCandidate(**payload)


def load_from_fixture(path: str | None) -> Tuple[List[TradeCandidate], PhaseContext]:
    file_path = Path(path) if path else FIXTURE_DIR / "cio_inputs.json"
    data = _load_json(file_path)
    candidates = [_trade_candidate_from_dict(c) for c in data.get("candidates", [])]
    for c in candidates:
        if not c.market_data_source:
            c.market_data_source = "fixture"
    ctx_data = data.get("context", {})
    sources = dict(ctx_data.get("research_data_sources") or {})
    board = list(ctx_data.get("research_board_lines") or [])
    if not sources or not board:
        auto_s, auto_b = _research_board_from_candidates(candidates)
        sources = sources or auto_s
        board = board or auto_b
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
        research_data_sources=sources,
        research_board_lines=board,
        research_ohlcv_note=ctx_data.get(
            "research_ohlcv_note",
            "OHLCV is research-only (IBKR when enabled → Schwab → yfinance). "
            "Live orders stay on Schwab — IBKR never places trades here.",
        ),
    )
    return candidates, context


_SECTOR_BY_SYMBOL = {
    "AAPL": "Technology", "MSFT": "Technology", "NVDA": "Technology",
    "AMZN": "Consumer", "META": "Technology", "GOOGL": "Technology",
    "TSLA": "Consumer", "AMD": "Technology", "JPM": "Financials",
    "SPY": "Broad Market", "QQQ": "Technology", "IWM": "Small Cap",
    "DIA": "Broad Market", "XLK": "Technology", "SMH": "Technology",
    "SOXX": "Technology", "XBI": "Healthcare", "XLE": "Energy",
    "XLF": "Financials", "GLD": "Commodities", "TLT": "Bonds",
}


def _candidate_from_ranked(item: dict, rank: int) -> TradeCandidate:
    symbol = item["symbol"]
    return TradeCandidate(
        symbol=symbol,
        direction=item.get("direction", "Bullish"),
        strategy=item.get("strategy", "Debit Call Spread"),
        entry_price=float(item.get("entry_price", 0)),
        strike_prices=item.get("strike_prices", []),
        expiration=item.get("expiration", ""),
        profit_target=float(item.get("profit_target", 0)),
        stop_loss=float(item.get("stop_loss", 0)),
        maximum_risk=float(item.get("maximum_risk", 100)),
        maximum_reward=float(item.get("maximum_reward", 250)),
        probability_of_success=float(item.get("probability_of_success", 0.5)),
        confidence_score=float(item.get("confidence_score", 60)),
        primary_catalyst="research pipeline",
        catalyst_type="technical",
        technical_summary="Phase 1 ranked opportunity",
        technical_confirmations=["trend:uptrend", "research:passed", "risk:approved"],
        options_summary="Liquidity screened in Phase 1",
        open_interest=5000,
        daily_options_volume=10000,
        bid_ask_spread_pct=2.0,
        iv_rank=35.0,
        expected_move_pct=4.0,
        probability_of_profit=float(item.get("probability_of_success", 0.5)),
        liquidity_score=70.0,
        sector=_SECTOR_BY_SYMBOL.get(symbol, item.get("sector", "Unknown")),
        correlation_group=_SECTOR_BY_SYMBOL.get(symbol, "General"),
        phase1_rank=rank,
    )


def _research_board_from_candidates(candidates: List[TradeCandidate]) -> tuple[dict, list]:
    """Build CIO-facing research board (sources + display lines)."""
    sources: dict[str, str] = {}
    lines: list[str] = []
    for c in candidates:
        src = (getattr(c, "market_data_source", None) or "unknown").strip() or "unknown"
        sources[c.symbol] = src
        tag = src.upper() if src != "unknown" else "?"
        lines.append(
            f"#{c.phase1_rank} **{c.symbol}** [{getattr(c, 'setup_grade', 'C') or 'C'}] "
            f"{c.direction} {c.strategy} | conf {c.confidence_score:.0f} | "
            f"bars=`{tag}`"
        )
    return sources, lines


def build_cio_context_from_plan(plan: DailyTradingPlan, intraday_flags: dict | None = None) -> PhaseContext:
    rs = plan.research_summary or {}
    sources = dict(rs.get("ohlcv_sources") or {})
    return PhaseContext(
        overall_market_bias=plan.overall_market_bias,
        market_environment_score=plan.market_environment_score,
        market_regime=infer_market_regime(plan.overall_market_bias),
        stay_in_cash=plan.stay_in_cash,
        intraday_flags=intraday_flags or {},
        research_data_sources=sources,
        research_ohlcv_note=str(
            rs.get("ohlcv_research_note")
            or (
                "OHLCV is research-only (IBKR when enabled → Schwab → yfinance). "
                "Live orders stay on Schwab — IBKR never places trades here."
            )
        ),
    )


def build_cio_approval_inputs(
    plan: DailyTradingPlan,
    fixture_mode: bool,
) -> Tuple[List[TradeCandidate], PhaseContext]:
    context = build_cio_context_from_plan(plan)
    if plan.ranked_opportunities:
        candidates = []
        for opp in plan.ranked_opportunities:
            sector = _SECTOR_BY_SYMBOL.get(opp.symbol, "Unknown")
            direction = getattr(opp, "direction", None) or (
                "Bullish" if opp.technical.trend == "uptrend"
                else "Bearish" if opp.technical.trend == "downtrend"
                else "Neutral"
            )
            bar_src = (
                getattr(opp, "market_data_source", None)
                or (plan.research_summary or {}).get("ohlcv_sources", {}).get(opp.symbol)
                or ("fixture" if fixture_mode else "unknown")
            )
            confirmations = [
                f"trend:{opp.technical.trend}",
                f"macd:{opp.technical.macd_signal}",
                f"vwap:{opp.technical.vwap_relation}",
                f"ma:{opp.technical.ma_alignment}",
                f"momentum:{getattr(opp.technical, 'momentum', 'neutral')}",
                f"ohlcv:{bar_src}",
            ]
            candidates.append(
                TradeCandidate(
                    symbol=opp.symbol,
                    direction=direction,
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
                    primary_catalyst=opp.supporting_reasons[0] if opp.supporting_reasons else "technical",
                    catalyst_type="technical_breakout" if "breakout" in (opp.technical.breakout_state or "") else "technical",
                    technical_summary=(
                        f"Trend {opp.technical.trend}, RSI {opp.technical.rsi:.0f}, "
                        f"ADX {opp.technical.adx:.0f}, TF {opp.technical.timeframe_alignment} "
                        f"[bars:{bar_src}]"
                    ),
                    technical_confirmations=confirmations,
                    options_summary=f"IV rank {opp.options.iv_rank:.0f}, liquidity {opp.options.liquidity_score:.0f}",
                    open_interest=max(int(opp.options.liquidity_score * 100), 1000),
                    daily_options_volume=max(int(getattr(opp.options, "options_volume", 0) or 5000), 1000),
                    bid_ask_spread_pct=float(getattr(opp.options, "bid_ask_spread_pct", 2.0) or 2.0),
                    iv_rank=opp.options.iv_rank,
                    expected_move_pct=opp.options.expected_move_pct,
                    probability_of_profit=opp.options.probability_of_profit,
                    liquidity_score=opp.options.liquidity_score,
                    sector=sector,
                    correlation_group=sector,
                    phase1_rank=opp.rank,
                    setup_grade=getattr(opp, "setup_grade", "C") or "C",
                    grade_score=float(getattr(opp, "grade_score", 0.0) or 0.0),
                    hold_style=getattr(opp, "hold_style", "") or "",
                    market_data_source=str(bar_src),
                )
            )
        sources, board = _research_board_from_candidates(candidates)
        context.research_data_sources = sources
        context.research_board_lines = board
        candidates, context, _ = _merge_researcher_cio(candidates, context)
        sources, board = _research_board_from_candidates(candidates)
        # keep researcher banner lines if merge prepended them
        banner = [
            ln
            for ln in (context.research_board_lines or [])
            if "Researcher" in ln or "researcher" in ln
        ]
        context.research_data_sources = {**(context.research_data_sources or {}), **sources}
        context.research_board_lines = banner + [ln for ln in board if ln not in banner]
        return candidates, context
    if fixture_mode:
        candidates, fixture_ctx = load_from_fixture(None)
        for c in candidates:
            if not getattr(c, "market_data_source", None):
                c.market_data_source = "fixture"
        sources, board = _research_board_from_candidates(candidates)
        context = PhaseContext(
            overall_market_bias=plan.overall_market_bias,
            market_environment_score=plan.market_environment_score,
            market_regime=infer_market_regime(plan.overall_market_bias),
            stay_in_cash=plan.stay_in_cash,
            intraday_flags=fixture_ctx.intraday_flags,
            strategy_refinement=fixture_ctx.strategy_refinement,
            sector_refinement=fixture_ctx.sector_refinement,
            weakest_strategies=fixture_ctx.weakest_strategies,
            performance_notes=fixture_ctx.performance_notes,
            research_data_sources=sources or dict(fixture_ctx.research_data_sources or {}),
            research_board_lines=board or list(fixture_ctx.research_board_lines or []),
            research_ohlcv_note=fixture_ctx.research_ohlcv_note
            or context.research_ohlcv_note,
        )
        candidates, context, _ = _merge_researcher_cio(candidates, context)
        return candidates, context
    # Even with empty Phase-1 book, CIO still reviews researcher lists
    candidates, context, _ = _merge_researcher_cio([], context)
    if candidates:
        sources, board = _research_board_from_candidates(candidates)
        banner = [
            ln
            for ln in (context.research_board_lines or [])
            if "Researcher" in ln or "researcher" in ln
        ]
        context.research_data_sources = {**(context.research_data_sources or {}), **sources}
        context.research_board_lines = banner + board
    return candidates, context


def _merge_researcher_cio(
    candidates: List[TradeCandidate],
    context: PhaseContext,
) -> Tuple[List[TradeCandidate], PhaseContext, dict]:
    try:
        from trading_agent.export.researcher_cio import merge_researcher_into_cio_candidates

        return merge_researcher_into_cio_candidates(candidates, context)
    except Exception:
        return candidates, context, {"enabled": False, "error": "merge_failed"}


def load_from_session_dir(
    session_dir: Path,
    mode: Literal["approval", "review"] = "approval",
) -> Tuple[List[TradeCandidate], PhaseContext]:
    inputs_path = session_dir / "cio_inputs.json"
    if not inputs_path.exists():
        raise FileNotFoundError(f"Missing CIO inputs at {inputs_path}")

    data = _load_json(inputs_path)
    candidates = [_trade_candidate_from_dict(c) for c in data.get("candidates", [])]
    ctx_data = dict(data.get("context", {}))

    if mode == "review":
        perf_path = session_dir / "performance_report.json"
        if perf_path.exists():
            perf = _load_json(perf_path)
            refinement = perf.get("refinement", {})
            patterns = perf.get("patterns", {})
            ctx_data["strategy_refinement"] = refinement.get("strategy_adjustments", {})
            ctx_data["sector_refinement"] = refinement.get("sector_adjustments", {})
            ctx_data["weakest_strategies"] = patterns.get("weakest_strategies", [])
            ctx_data["performance_notes"] = perf.get("lessons_learned", [])[:5]
        flags_path = session_dir / "intraday_flags.json"
        if flags_path.exists():
            ctx_data["intraday_flags"] = _load_json(flags_path)

    sources = dict(ctx_data.get("research_data_sources") or {})
    board = list(ctx_data.get("research_board_lines") or [])
    if candidates and (not sources or not board):
        auto_s, auto_b = _research_board_from_candidates(candidates)
        sources = sources or auto_s
        board = board or auto_b
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
        research_data_sources=sources,
        research_board_lines=board,
        research_ohlcv_note=ctx_data.get(
            "research_ohlcv_note",
            "OHLCV is research-only (IBKR when enabled → Schwab → yfinance). "
            "Live orders stay on Schwab — IBKR never places trades here.",
        ),
    )
    # Re-merge latest local researcher books at CIO load time (post-pull)
    candidates, context, _ = _merge_researcher_cio(candidates, context)
    return candidates, context


def load_from_pipelines() -> Tuple[List[TradeCandidate], PhaseContext]:
    """Synthesize CIO inputs by running Phase 1–3 pipelines in fixture mode."""
    from trading_agent.intraday.pipeline import run_intraday_pipeline
    from trading_agent.performance.pipeline import run_performance_pipeline
    from trading_agent.pipeline import run_pipeline

    plan = run_pipeline(AgentConfig(fixture_mode=True, use_live_data=False))
    intraday = run_intraday_pipeline(IntradayConfig(fixture_mode=True, use_live_data=False))
    performance = run_performance_pipeline(PerformanceConfig(fixture_mode=True))

    candidates, context = build_cio_approval_inputs(plan, fixture_mode=True)
    intraday_flags = {r.symbol: r.action for r in intraday.recommendations}
    context.intraday_flags = intraday_flags
    context.strategy_refinement = performance.refinement.strategy_adjustments
    context.sector_refinement = performance.refinement.sector_adjustments
    context.weakest_strategies = performance.patterns.weakest_strategies
    context.performance_notes = performance.lessons_learned[:3]
    return candidates, context


def load_cio_inputs(
    fixture_mode: bool,
    inputs_file: str | None,
    session_dir: Path | None = None,
    mode: Literal["approval", "review"] = "approval",
) -> Tuple[List[TradeCandidate], PhaseContext]:
    if session_dir and (session_dir / "cio_inputs.json").exists():
        return load_from_session_dir(session_dir, mode=mode)
    if fixture_mode:
        return load_from_fixture(inputs_file)
    try:
        candidates, context = load_from_pipelines()
        if candidates or context.stay_in_cash:
            return candidates, context
    except Exception:
        pass
    return load_from_fixture(inputs_file)