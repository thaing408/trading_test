"""Orchestrate the full pre-market research pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from trading_agent.analysis.options import compute_options_metrics
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
    MarketSnapshot,
    OptionsMetrics,
    RejectedSetup,
    ScreenerCandidate,
    TechnicalAnalysis,
    TradeOpportunity,
)
from trading_agent.ranking.ranker import build_opportunities
from trading_agent.risk.manager import evaluate_risk


def _compute_market_bias(snapshot: MarketSnapshot) -> Tuple[str, float]:
    score = 50.0
    signals: List[str] = []

    es = snapshot.futures.get("ES", {})
    nq = snapshot.futures.get("NQ", {})
    vix = snapshot.vix.get("VIX", {})

    if es.get("change_pct", 0) > 0.3:
        score += 8
        signals.append("S&P futures positive overnight")
    elif es.get("change_pct", 0) < -0.3:
        score -= 8
        signals.append("S&P futures negative overnight")

    if nq.get("change_pct", 0) > 0.3:
        score += 5
    elif nq.get("change_pct", 0) < -0.3:
        score -= 5

    vix_level = vix.get("last", 20)
    if vix_level and vix_level < 18:
        score += 5
        signals.append("VIX subdued — risk-on tone")
    elif vix_level and vix_level > 25:
        score -= 10
        signals.append("Elevated VIX — caution warranted")

    sectors = snapshot.sector_rotation
    if sectors:
        leaders = sorted(sectors.items(), key=lambda x: x[1].get("change_pct", 0), reverse=True)
        if leaders:
            signals.append(f"Sector leader: {leaders[0][0]}")

    if score >= 58:
        bias = "Bullish — risk-on pre-market conditions favor selective long premium or bullish spreads"
    elif score <= 42:
        bias = "Bearish — defensive positioning favored; favor hedges or cash-secured strategies"
    else:
        bias = "Neutral — mixed overnight signals; favor defined-risk premium strategies"

    if signals:
        bias += f" ({'; '.join(signals[:3])})"

    return bias, round(min(100.0, max(0.0, score)), 1)


def _get_ohlcv(symbol: str) -> Dict[str, List[float]]:
    if symbol == "__fixture__":
        from trading_agent.collectors.base import load_fixture

        data = load_fixture("ohlcv.json")
        return data.get(symbol, data.get("SPY", {}))

    import yfinance as yf

    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="3mo", interval="1d")
    if hist.empty:
        return {"close": [], "high": [], "low": [], "volume": []}
    return {
        "close": hist["Close"].tolist(),
        "high": hist["High"].tolist(),
        "low": hist["Low"].tolist(),
        "volume": hist["Volume"].tolist(),
    }


def _analyze_candidate(
    candidate: ScreenerCandidate,
    config: AgentConfig,
    benchmark_closes: List[float] | None = None,
) -> Tuple[TechnicalAnalysis, OptionsMetrics]:
    if config.fixture_mode:
        from trading_agent.collectors.base import load_fixture

        data = load_fixture("ohlcv.json").get(candidate.symbol, {})
        closes = data.get("close", [])
        highs = data.get("high", [])
        lows = data.get("low", [])
        volumes = data.get("volume", [])
        iv_history = data.get("iv_history", [0.25, 0.28, 0.30, 0.27])
        iv = data.get("iv", 0.28)
    else:
        ohlcv = _get_ohlcv(candidate.symbol)
        closes = ohlcv["close"]
        highs = ohlcv["high"]
        lows = ohlcv["low"]
        volumes = ohlcv["volume"]
        returns = [
            abs((closes[i] - closes[i - 1]) / closes[i - 1]) * 100
            for i in range(1, len(closes))
        ] if len(closes) > 1 else [25.0]
        iv_history = returns[-30:] if len(returns) >= 30 else returns
        iv = float(sum(iv_history) / len(iv_history)) * 3.65 if iv_history else 25.0

    bench = benchmark_closes
    if bench is None and not config.fixture_mode:
        bench = _get_ohlcv("SPY")["close"]

    technical = compute_technical_analysis(
        candidate.symbol, closes, highs, lows, volumes, bench
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
    )
    return technical, options


def run_pipeline(config: AgentConfig) -> DailyTradingPlan:
    market = collect_market_snapshot(config)
    calendar = collect_economic_calendar(config)
    screener = collect_screener_candidates(config)
    symbols = [c.symbol for c in screener.candidates]
    news = collect_news_catalysts(config, symbols)

    bias, env_score = _compute_market_bias(market)

    bench_closes = None
    if config.fixture_mode:
        from trading_agent.collectors.base import load_fixture

        bench_closes = load_fixture("ohlcv.json").get("SPY", {}).get("close")

    analyzed: List[Tuple[ScreenerCandidate, TechnicalAnalysis, OptionsMetrics]] = []
    for candidate in screener.candidates:
        technical, options = _analyze_candidate(candidate, config, bench_closes)
        analyzed.append((candidate, technical, options))

    qualified, rejected = evaluate_risk(analyzed, config.risk)

    low_confidence_rejected: List[RejectedSetup] = []
    opportunities: List[TradeOpportunity] = build_opportunities(qualified, config.risk)

    qualified_symbols = {q[0].symbol for q in qualified}
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

    all_rejections = rejected + low_confidence_rejected
    stay_in_cash = len(opportunities) == 0
    cash_reason = ""
    if stay_in_cash:
        cash_reason = (
            "Capital preservation priority: no setups passed all risk management standards "
            f"({len(all_rejections)} rejected). Recommend staying in cash until higher-quality "
            "opportunities emerge."
        )

    watchlist = sorted(
        screener.candidates,
        key=lambda c: c.relative_volume,
        reverse=True,
    )[:10]
    top_watchlist = [c.symbol for c in watchlist]

    errors: List[str] = []
    errors.extend(market.errors)
    errors.extend(calendar.errors)
    errors.extend(news.errors)
    errors.extend(screener.errors)

    research_summary: Dict[str, Any] = {
        "market_source": market.source,
        "calendar_source": calendar.source,
        "news_source": news.source,
        "screener_source": screener.source,
        "candidates_screened": len(screener.candidates),
        "qualified_count": len(qualified),
        "calendar_events": len(calendar.events),
        "news_items": len(news.items),
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