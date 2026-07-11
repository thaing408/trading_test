"""Rank qualified setups by confidence and trade quality."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Tuple

from trading_agent.config import RiskConfig
from trading_agent.models import (
    OptionsMetrics,
    ScreenerCandidate,
    TechnicalAnalysis,
    TradeOpportunity,
)
from trading_agent.strategy.selector import StrategySelection, select_strategy


def compute_confidence_score(
    technical: TechnicalAnalysis,
    options: OptionsMetrics,
    candidate: ScreenerCandidate,
) -> float:
    iv_component = (
        (100 - min(options.iv_rank, 100)) * 0.05
        if options.iv_rank > 50
        else options.iv_rank * 0.05 + 2.5
    )
    score = (
        technical.score * 0.35
        + options.liquidity_score * 0.20
        + options.probability_of_profit * 100 * 0.25
        + min(candidate.relative_volume, 3.0) / 3.0 * 100 * 0.10
        + iv_component
    )
    if options.unusual_activity:
        score += 5
    if candidate.institutional_score:
        score += min(5.0, candidate.institutional_score / 20.0)
    return round(min(100.0, max(0.0, score)), 1)


def compute_trade_quality_score(
    technical: TechnicalAnalysis,
    options: OptionsMetrics,
    candidate: ScreenerCandidate,
    confidence: float,
) -> float:
    """Composite 0-100 quality: technicals, liquidity, POP, confidence, institutional."""
    quality = (
        technical.score * 0.30
        + options.liquidity_score * 0.20
        + options.probability_of_profit * 100 * 0.20
        + confidence * 0.20
        + min(100.0, candidate.institutional_score or 50.0) * 0.10
    )
    if technical.timeframe_alignment == "aligned_bullish" or technical.timeframe_alignment == "aligned_bearish":
        quality += 5
    if technical.breakout_state in ("breakout", "breakdown"):
        quality += 2
    if options.bid_ask_spread_pct and options.bid_ask_spread_pct > 3:
        quality -= 5
    return round(min(100.0, max(0.0, quality)), 1)


def _trade_params(
    price: float,
    strategy: StrategySelection,
    options: OptionsMetrics,
    technical: TechnicalAnalysis,
) -> dict:
    atr = technical.atr or price * 0.02
    risk_unit = max(price * 0.02, atr)
    # Institutional floor: CIO min R:R is typically 2:1 — size reward leg accordingly
    if strategy.name in ("Iron Condor", "Bull Put Credit Spread", "Bear Call Credit Spread"):
        max_risk = round(risk_unit * 1.5, 2)
        max_reward = round(risk_unit * 3.0, 2)  # defined-risk credit R:R proxy ≥ 2
    elif "Spread" in strategy.name or strategy.name in ("Calendar Spread", "Diagonal Spread"):
        max_risk = round(risk_unit * 1.5, 2)
        max_reward = round(risk_unit * 3.0, 2)
    elif strategy.name in ("Long Call", "Long Put"):
        max_risk = round(risk_unit * 2.5, 2)
        max_reward = round(risk_unit * 5.0, 2)
    elif strategy.name in ("Covered Call", "Cash Secured Put"):
        # Premium strategies: reward = credit proxy, risk = assignment buffer — target ≥2:1 quality bar
        max_risk = round(risk_unit, 2)
        max_reward = round(risk_unit * 2.2, 2)
    else:
        max_risk = round(risk_unit, 2)
        max_reward = round(risk_unit * 2.0, 2)

    if strategy.direction == "Bearish":
        profit_target = round(price - max_reward * 0.01 * price / 100 * 100, 2)
        # clearer: move price by ATR fraction
        profit_target = round(price - atr * 1.5, 2)
        stop_loss = round(price + atr, 2)
    else:
        profit_target = round(price + atr * 1.5, 2)
        stop_loss = round(price - atr, 2)

    return {
        "entry_price": round(price, 2),
        "profit_target": profit_target,
        "stop_loss": stop_loss,
        "maximum_risk": max_risk,
        "maximum_reward": max_reward,
        "probability_of_success": options.probability_of_profit,
    }


def _thesis(
    candidate: ScreenerCandidate,
    technical: TechnicalAnalysis,
    options: OptionsMetrics,
    strategy: StrategySelection,
) -> str:
    tf = ", ".join(
        f"{k}={v}"
        for k, v in technical.timeframe_trends.items()
        if k != "intraday" and v != "unavailable"
    )
    pattern_bit = ""
    if technical.pattern_summary and technical.pattern_summary != "none":
        pattern_bit = f", patterns={technical.pattern_summary}"
    return (
        f"{strategy.direction} {strategy.name} on {candidate.symbol}: "
        f"trend={technical.trend}, momentum={technical.momentum}, "
        f"breakout={technical.breakout_state}, RS={technical.relative_strength}"
        f"{pattern_bit}, "
        f"IVR={options.iv_rank}, POP={options.probability_of_profit:.0%}, "
        f"flow={options.institutional_flow_bias}; multi-TF [{tf}]"
    )


def _risks(
    candidate: ScreenerCandidate,
    technical: TechnicalAnalysis,
    options: OptionsMetrics,
    strategy: StrategySelection,
) -> List[str]:
    risks: List[str] = []
    if technical.timeframe_alignment == "conflicting":
        risks.append("Conflicting multi-timeframe trends")
    if options.iv_rank >= 70:
        risks.append("Elevated IV rank — premium expensive / vol crush risk")
    if options.iv_rank <= 25 and strategy.name in ("Long Call", "Long Put"):
        risks.append("Low IV with long premium — needs expansion for payoff")
    if candidate.bid_ask_spread_pct > 2.0:
        risks.append(f"Options bid/ask {candidate.bid_ask_spread_pct}% — slippage risk")
    if technical.adx < 20:
        risks.append("Weak trend strength (ADX < 20)")
    if technical.breakout_state == "none" and strategy.direction != "Neutral":
        risks.append("No confirmed breakout/breakdown at entry")
    if options.probability_of_touch > 0.7 and "Credit" in strategy.name:
        risks.append("High probability of touch on short strikes")
    # Institutional PA traps (cheat-sheet) — caution when conflicting with trade direction
    for name in technical.pa_signals or []:
        if "fakeout" in name or "stop_hunt_supply" in name:
            if strategy.direction == "Bullish" and ("breakout" in name or "supply" in name):
                risks.append(f"Institutional PA caution: {name} (fakeout/stop-hunt trap risk)")
        if "stop_hunt_demand" in name and strategy.direction == "Bearish":
            risks.append(f"Institutional PA caution: {name} (demand liquidity grab)")
        if name in ("shooting_star",) or name.endswith("bearish"):
            if strategy.direction == "Bullish":
                risks.append(f"Bearish PA/candle context: {name}")
    for name in technical.candle_patterns or []:
        if name in ("shooting_star", "bearish_engulfing", "doji") and strategy.direction == "Bullish":
            risks.append(f"Candlestick caution: {name}")
        if name in ("hammer", "bullish_engulfing") and strategy.direction == "Bearish":
            risks.append(f"Candlestick caution: {name}")
    if not risks:
        risks.append("Standard gap and event risk into the session")
    return risks[:6]


def build_opportunities(
    qualified: List[Tuple[ScreenerCandidate, TechnicalAnalysis, OptionsMetrics]],
    risk_config: RiskConfig,
    max_count: int | None = None,
) -> List[TradeOpportunity]:
    limit = max_count if max_count is not None else risk_config.top_candidates
    scored: List[Tuple[float, ScreenerCandidate, TechnicalAnalysis, OptionsMetrics, StrategySelection]] = []

    for candidate, technical, options in qualified:
        confidence = compute_confidence_score(technical, options, candidate)
        if confidence < risk_config.min_confidence_score:
            continue
        strategy = select_strategy(technical, options, candidate.price)
        scored.append((confidence, candidate, technical, options, strategy))

    scored.sort(key=lambda x: x[0], reverse=True)
    opportunities: List[TradeOpportunity] = []

    for rank, (confidence, candidate, technical, options, strategy) in enumerate(scored[:limit], 1):
        params = _trade_params(candidate.price, strategy, options, technical)
        expiry = (datetime.now() + timedelta(days=strategy.expiration_days)).strftime("%Y-%m-%d")
        quality = compute_trade_quality_score(technical, options, candidate, confidence)
        thesis = _thesis(candidate, technical, options, strategy)
        risks = _risks(candidate, technical, options, strategy)
        tf_summary = ", ".join(
            f"{k}={v}" for k, v in technical.timeframe_trends.items() if k != "intraday"
        )
        reasons = [
            f"Multi-timeframe: {tf_summary} (alignment: {technical.timeframe_alignment})",
            f"EMAs 9/20/50/200: {technical.ema_9:.2f}/{technical.ema_20:.2f}/"
            f"{technical.ema_50:.2f}/{technical.ema_200:.2f}; MA={technical.ma_alignment}",
            f"RSI {technical.rsi}, MACD {technical.macd_signal}, ADX {technical.adx}, "
            f"ATR {technical.atr}, BB {technical.bollinger_position}, VWAP {technical.vwap_relation}",
            f"Breakout={technical.breakout_state}, momentum={technical.momentum}, "
            f"volume profile={technical.volume_profile_bias}, RS={technical.relative_strength}",
            f"Candles={','.join(technical.candle_patterns) or 'none'}; "
            f"institutional PA={','.join(technical.pa_signals) or 'none'} "
            f"({technical.pattern_summary})",
            f"Options IV {options.implied_volatility} IVR {options.iv_rank} IVP {options.iv_percentile} "
            f"EM {options.expected_move_pct}% POP {options.probability_of_profit} "
            f"POT {options.probability_of_touch} liq {options.liquidity_score} "
            f"flow {options.institutional_flow_bias}",
            f"Strategy {strategy.name} ({strategy.direction})",
            f"RVOL {candidate.relative_volume}x, OI {candidate.open_interest}, "
            f"institutional score {candidate.institutional_score}",
        ]
        opportunities.append(
            TradeOpportunity(
                rank=rank,
                symbol=candidate.symbol,
                strategy=strategy.name,
                entry_price=params["entry_price"],
                strike_prices=strategy.strike_prices,
                expiration=expiry,
                profit_target=params["profit_target"],
                stop_loss=params["stop_loss"],
                maximum_risk=params["maximum_risk"],
                maximum_reward=params["maximum_reward"],
                probability_of_success=params["probability_of_success"],
                confidence_score=confidence,
                supporting_reasons=reasons,
                technical=technical,
                options=options,
                direction=strategy.direction,
                trade_thesis=thesis,
                trade_quality_score=quality,
                risks=risks,
            )
        )

    return opportunities
