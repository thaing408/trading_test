"""Options-specific metrics evaluation (pure functions)."""

from __future__ import annotations

from typing import Sequence

import numpy as np

from trading_agent.models import OptionsMetrics


def iv_rank(current_iv: float, iv_history: Sequence[float]) -> float:
    if not iv_history:
        return 50.0
    low, high = min(iv_history), max(iv_history)
    if high == low:
        return 50.0
    return round((current_iv - low) / (high - low) * 100, 2)


def iv_percentile(current_iv: float, iv_history: Sequence[float]) -> float:
    if not iv_history:
        return 50.0
    below = sum(1 for v in iv_history if v <= current_iv)
    return round(below / len(iv_history) * 100, 2)


def expected_move_pct(price: float, iv: float, days: int = 30) -> float:
    if price <= 0:
        return 0.0
    return round(price * (iv / 100) * np.sqrt(days / 365) / price * 100, 2)


def black_scholes_delta(price: float, strike: float, iv: float, days: int, call: bool = True) -> float:
    if price <= 0 or strike <= 0 or days <= 0:
        return 0.5
    t = days / 365
    d1 = (np.log(price / strike) + 0.5 * (iv / 100) ** 2 * t) / ((iv / 100) * np.sqrt(t) + 1e-9)
    from math import erf, sqrt

    nd1 = 0.5 * (1 + erf(d1 / sqrt(2)))
    return round(nd1 if call else nd1 - 1, 4)


def estimate_greeks(price: float, strike: float, iv: float, days: int) -> tuple[float, float, float, float]:
    t = max(days / 365, 1 / 365)
    delta = black_scholes_delta(price, strike, iv, days, call=True)
    gamma = round(0.01 * (1 / (price * (iv / 100) * np.sqrt(t) + 1e-9)), 4)
    theta = round(-price * (iv / 100) / (2 * np.sqrt(t) * 365), 4)
    vega = round(price * np.sqrt(t) / 100, 4)
    return delta, gamma, theta, vega


def probability_of_profit(delta: float, strategy_bias: str) -> float:
    base = abs(delta)
    if strategy_bias == "bullish":
        return round(min(0.85, max(0.35, 0.5 + base * 0.3)), 2)
    if strategy_bias == "bearish":
        return round(min(0.85, max(0.35, 0.5 + (1 - abs(delta)) * 0.2)), 2)
    return round(min(0.75, max(0.40, 0.5 + base * 0.15)), 2)


def compute_options_metrics(
    symbol: str,
    price: float,
    iv: float,
    iv_history: Sequence[float],
    strike: float,
    days_to_expiry: int,
    open_interest: int,
    relative_volume: float,
    bid_ask_spread_pct: float,
    trend: str,
) -> OptionsMetrics:
    delta, gamma, theta, vega = estimate_greeks(price, strike, iv, days_to_expiry)
    unusual = relative_volume >= 1.5 and open_interest >= 500
    flow_bias = "bullish" if trend == "uptrend" else "bearish" if trend == "downtrend" else "neutral"
    liquidity = min(100.0, max(0.0, 100 - bid_ask_spread_pct * 4 + open_interest / 100))
    pop = probability_of_profit(delta, flow_bias)
    return OptionsMetrics(
        symbol=symbol,
        implied_volatility=round(iv, 2),
        iv_rank=iv_rank(iv, iv_history),
        iv_percentile=iv_percentile(iv, iv_history),
        expected_move_pct=expected_move_pct(price, iv, days_to_expiry),
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
        unusual_activity=unusual,
        institutional_flow_bias=flow_bias,
        liquidity_score=round(liquidity, 1),
        probability_of_profit=pop,
    )