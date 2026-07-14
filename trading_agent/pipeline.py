"""Orchestrate the full pre-market research pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from trading_agent.analysis.options import compute_options_metrics
from trading_agent.analysis.strength import evaluate_premarket_gates, evaluate_strength_gates
from trading_agent.analysis.technical import compute_technical_analysis
from trading_agent.collectors import (
    collect_economic_calendar,
    collect_market_snapshot,
    collect_news_catalysts,
    collect_screener_candidates,
)
from trading_agent.config import AgentConfig
from trading_agent.models import (
    DailyTradingPlan,
    OptionsMetrics,
    RejectedSetup,
    ScreenerCandidate,
    TechnicalAnalysis,
    TradeOpportunity,
)
from trading_agent.ranking.ranker import build_opportunities
from trading_agent.risk.manager import evaluate_risk
from trading_agent.screener_params import get_screener_params
from trading_agent.synthesis.market_context import build_watchlist, synthesize_market_context


def _get_ohlcv(
    symbol: str,
    config: AgentConfig,
    interval: str = "1d",
    period: str = "3mo",
) -> Dict[str, List[float]]:
    """OHLCV for TR strength gates + technicals (Schwab-first when configured/auto)."""
    from trading_agent.market_data import get_ohlcv

    return get_ohlcv(symbol, config, interval=interval, period=period)


def _analyze_candidate(
    candidate: ScreenerCandidate,
    config: AgentConfig,
    benchmark_closes: List[float] | None = None,
) -> Tuple[TechnicalAnalysis, OptionsMetrics]:
    bars_30m: List[float] | None = None
    bars_15m: List[float] | None = None
    opens: List[float] | None = None
    if config.fixture_mode:
        from trading_agent.collectors.base import load_fixture

        data = load_fixture("ohlcv.json").get(candidate.symbol, {})
        closes = data.get("close", [])
        highs = data.get("high", [])
        lows = data.get("low", [])
        volumes = data.get("volume", [])
        opens = data.get("open") or None
        hourly = data.get("hourly", {})
        iv_history = data.get("iv_history", [0.25, 0.28, 0.30, 0.27])
        iv = data.get("iv", 0.28)
        # Scale fixture IV if stored as fraction
        if iv < 1.5:
            iv = iv * 100
            iv_history = [v * 100 if v < 1.5 else v for v in iv_history]
        intraday = {
            "close": hourly.get("close", []),
            "high": hourly.get("high", []),
            "low": hourly.get("low", []),
            "volume": hourly.get("volume", []),
        }
        bars_30m = data.get("m30", {}).get("close")
        bars_15m = data.get("m15", {}).get("close")
        # Synthesize lower TFs from hourly when fixture omits them
        if not bars_30m and intraday.get("close"):
            bars_30m = list(intraday["close"])  # best-effort proxy
        if not bars_15m and intraday.get("close"):
            bars_15m = list(intraday["close"])
    else:
        daily = _get_ohlcv(candidate.symbol, config, interval="1d", period="1y")
        intraday_ohlcv = _get_ohlcv(candidate.symbol, config, interval="1h", period="10d")
        m30 = _get_ohlcv(candidate.symbol, config, interval="30m", period="5d")
        m15 = _get_ohlcv(candidate.symbol, config, interval="15m", period="5d")
        closes = daily["close"]
        highs = daily["high"]
        lows = daily["low"]
        volumes = daily["volume"]
        opens = daily.get("open")
        intraday = intraday_ohlcv
        bars_30m = m30.get("close") or None
        bars_15m = m15.get("close") or None
        returns = [
            abs((closes[i] - closes[i - 1]) / closes[i - 1]) * 100
            for i in range(1, len(closes))
        ] if len(closes) > 1 else [25.0]
        iv_history = returns[-30:] if len(returns) >= 30 else returns
        iv = float(sum(iv_history) / len(iv_history)) * 3.65 if iv_history else 25.0

    bench = benchmark_closes
    if bench is None and not config.fixture_mode:
        bench = _get_ohlcv("SPY", config, interval="1d", period="1y")["close"]

    technical = compute_technical_analysis(
        candidate.symbol,
        closes,
        highs,
        lows,
        volumes,
        bench,
        intraday_closes=intraday.get("close"),
        intraday_highs=intraday.get("high"),
        intraday_lows=intraday.get("low"),
        intraday_volumes=intraday.get("volume"),
        bars_30m=bars_30m,
        bars_15m=bars_15m,
        opens=opens,
    )
    strike = round(candidate.price * (1.02 if technical.trend == "uptrend" else 0.98), 2)
    options = compute_options_metrics(
        symbol=candidate.symbol,
        price=candidate.price,
        iv=iv,
        iv_history=iv_history,
        strike=strike,
        days_to_expiry=30,
        open_interest=candidate.open_interest,
        relative_volume=candidate.relative_volume,
        bid_ask_spread_pct=candidate.bid_ask_spread_pct,
        trend=technical.trend,
        options_volume=candidate.options_volume,
    )
    return technical, options


def _candidate_ohlcv(symbol: str, config: AgentConfig) -> Dict[str, List[float]]:
    """Daily OHLCV for strength gates (fixture or live)."""
    bars = _get_ohlcv(symbol, config, interval="1d", period="1y")
    if config.fixture_mode:
        from trading_agent.collectors.base import load_fixture

        data = load_fixture("ohlcv.json").get(symbol, {})
        if "open" in data:
            bars["open"] = data["open"]
    return bars


def run_pipeline(config: AgentConfig) -> DailyTradingPlan:
    market = collect_market_snapshot(config)
    calendar = collect_economic_calendar(config)
    screener = collect_screener_candidates(config)
    symbols = [c.symbol for c in screener.candidates]
    news = collect_news_catalysts(config, symbols)

    context = synthesize_market_context(market, calendar, news)
    bias = context.bias
    env_score = context.environment_score

    bench_closes = None
    if config.fixture_mode:
        from trading_agent.collectors.base import load_fixture

        bench_closes = load_fixture("ohlcv.json").get("SPY", {}).get("close")

    analyzed: List[Tuple[ScreenerCandidate, TechnicalAnalysis, OptionsMetrics]] = []
    strength_rejected: List[RejectedSetup] = []
    strength_survivors: List[Tuple[ScreenerCandidate, TechnicalAnalysis, OptionsMetrics]] = []
    strength_params = get_screener_params()

    for candidate in screener.candidates:
        technical, options = _analyze_candidate(candidate, config, bench_closes)
        if config.apply_strength_gates:
            bars = _candidate_ohlcv(candidate.symbol, config)
            rvol = (
                candidate.premarket_relative_volume
                if candidate.premarket_relative_volume
                else candidate.relative_volume
            )
            strength = evaluate_strength_gates(
                bars.get("close", []),
                bars.get("high", []),
                bars.get("low", []),
                bars.get("volume", []),
                opens=bars.get("open") or None,
                relative_volume=rvol,
                gap_pct=candidate.gap_pct if candidate.gap_pct else None,
                params=strength_params.best_winners,
            )
            if not strength.passed:
                strength_rejected.append(
                    RejectedSetup(
                        symbol=candidate.symbol,
                        reason="; ".join(strength.reasons),
                    )
                )
                continue
            # Optional pre-market gap/RVOL: observe/prepare signal only (not auto-buy).
            # Hard strength gates already passed; soft-miss does not drop survivors.
            if config.apply_premarket_gap_rvol and strength.metrics is not None:
                strength.metrics.relative_volume = rvol
                if candidate.gap_pct:
                    strength.metrics.gap_pct = candidate.gap_pct
                evaluate_premarket_gates(
                    strength.metrics,
                    strength_eval=strength,
                    params=strength_params.pre_market,
                )
            strength_survivors.append((candidate, technical, options))
        analyzed.append((candidate, technical, options))

    qualified, rejected = evaluate_risk(analyzed, config.risk)

    low_confidence_rejected: List[RejectedSetup] = []
    opportunities: List[TradeOpportunity] = build_opportunities(qualified, config.risk)

    for candidate, technical, options in qualified:
        from trading_agent.ranking.ranker import compute_confidence_score

        conf = compute_confidence_score(technical, options, candidate)
        if conf < config.risk.min_confidence_score and candidate.symbol not in {o.symbol for o in opportunities}:
            low_confidence_rejected.append(
                RejectedSetup(
                    symbol=candidate.symbol,
                    reason=f"Confidence score {conf} below minimum {config.risk.min_confidence_score}",
                )
            )

    all_rejections = strength_rejected + rejected + low_confidence_rejected
    stay_in_cash = len(opportunities) == 0
    cash_reason = ""
    if stay_in_cash:
        cash_reason = (
            "Capital preservation priority: no setups passed all risk management standards "
            f"({len(all_rejections)} rejected). Recommend staying in cash until higher-quality "
            "opportunities emerge."
        )
        if strength_rejected:
            cash_reason += (
                f" Strength/pre-market screen rejected {len(strength_rejected)} "
                "(ADR%/52w/EMA/3m/dollar-volume or gap-RVOL gates)."
            )
        if context.high_impact_events:
            cash_reason += f" High-impact calendar: {context.high_impact_events[0]}."

    # Prefer strength survivors on watchlist when strength gates are active
    watch_pool = (
        [c for c, _, _ in strength_survivors]
        if config.apply_strength_gates and strength_survivors
        else screener.candidates
    )
    if config.apply_strength_gates and not strength_survivors:
        # All failed strength — still show symbols but rejections name the gates
        watch_pool = screener.candidates

    top_watchlist = build_watchlist(
        watch_pool,
        context,
        limit=config.risk.top_watchlist_size,
    )

    errors: List[str] = []
    errors.extend(market.errors)
    errors.extend(calendar.errors)
    errors.extend(news.errors)
    errors.extend(screener.errors)

    # Aggregate candlestick + institutional PA across analyzed names for research
    pattern_hits: List[str] = []
    for cand, tech, _ in analyzed:
        if tech.pattern_summary and tech.pattern_summary != "none":
            pattern_hits.append(f"{cand.symbol}: {tech.pattern_summary}")
    # Also scan strength rejects' technical if available — analyzed only survivors+passed path
    # Include rejections that still went through analysis (only analyzed list)
    research_summary: Dict[str, Any] = {
        "market_source": market.source,
        "calendar_source": calendar.source,
        "news_source": news.source,
        "screener_source": screener.source,
        "candidates_screened": len(screener.candidates),
        "rejected_count": len(all_rejections),
        "strength_screened": len(screener.candidates) if config.apply_strength_gates else 0,
        "strength_survivors": len(strength_survivors),
        "strength_rejected": len(strength_rejected),
        "strength_profile": strength_params.best_winners.name,
        "premarket_profile": strength_params.pre_market.name,
        "screener_params": {
            "min_adr_pct": strength_params.best_winners.min_adr_pct,
            "min_pct_above_52w_low": strength_params.best_winners.min_pct_above_52w_low,
            "ema_fast": strength_params.best_winners.ema_fast,
            "ema_slow": strength_params.best_winners.ema_slow,
            "min_performance_3m_pct": strength_params.best_winners.min_performance_3m_pct,
            "min_dollar_volume_avg_30d": strength_params.best_winners.min_dollar_volume_avg_30d,
            "min_dollar_volume_prior_day": strength_params.best_winners.min_dollar_volume_prior_day,
        },
        "pattern_signals": pattern_hits[:12],
        "candlestick_pa_note": (
            "Institutional PA + candles (stop-hunt, fakeout, QML retest, RS flip; "
            "hammer/engulfing/doji/shooting-star) inform research thesis and risk notes"
        ),
        "qualified_count": len(qualified),
        "calendar_events": len(calendar.events),
        "news_items": len(news.items),
        "calendar_summary": context.calendar_summary,
        "high_impact_events": context.high_impact_events,
        "news_highlights": context.news_highlights,
        "overnight_summary": context.overnight_summary,
        "market_signals": context.signals,
        "catalyst_symbols": list(context.catalyst_symbols.keys()),
        "top_candidates_cap": config.risk.top_candidates,
        "top_watchlist_cap": config.risk.top_watchlist_size,
        "errors": errors,
    }

    return DailyTradingPlan(
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        overall_market_bias=bias,
        market_environment_score=env_score,
        top_watchlist=top_watchlist,
        ranked_opportunities=opportunities,
        rejection_reasons=all_rejections,
        research_summary=research_summary,
        stay_in_cash=stay_in_cash,
        cash_recommendation_reason=cash_reason,
    )