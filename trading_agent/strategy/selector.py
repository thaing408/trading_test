"""Select appropriate defined options strategy for market conditions."""

from __future__ import annotations

from dataclasses import dataclass

from trading_agent.models import OptionsMetrics, TechnicalAnalysis


@dataclass
class StrategySelection:
    name: str
    strike_prices: list[float]
    expiration_days: int
    bias: str


def select_strategy(
    technical: TechnicalAnalysis,
    options: OptionsMetrics,
    price: float,
) -> StrategySelection:
    iv_high = options.iv_rank >= 60
    iv_low = options.iv_rank <= 35
    bullish = technical.trend == "uptrend" and technical.macd_signal != "bearish"
    bearish = technical.trend == "downtrend" and technical.macd_signal != "bullish"
    neutral = not bullish and not bearish

    if iv_high and neutral:
        width = round(price * 0.03, 2)
        return StrategySelection(
            name="Iron Condor",
            strike_prices=[
                round(price - width * 2, 2),
                round(price - width, 2),
                round(price + width, 2),
                round(price + width * 2, 2),
            ],
            expiration_days=30,
            bias="neutral",
        )
    if iv_high and bullish:
        return StrategySelection(
            name="Covered Call",
            strike_prices=[round(price * 1.05, 2)],
            expiration_days=30,
            bias="bullish",
        )
    if iv_high and bearish:
        return StrategySelection(
            name="Cash Secured Put",
            strike_prices=[round(price * 0.95, 2)],
            expiration_days=30,
            bias="bearish",
        )
    if iv_low and bullish:
        return StrategySelection(
            name="Debit Call Spread",
            strike_prices=[round(price, 2), round(price * 1.05, 2)],
            expiration_days=45,
            bias="bullish",
        )
    if iv_low and bearish:
        return StrategySelection(
            name="Debit Put Spread",
            strike_prices=[round(price, 2), round(price * 0.95, 2)],
            expiration_days=45,
            bias="bearish",
        )
    if bullish:
        return StrategySelection(
            name="Long Call",
            strike_prices=[round(price * 1.02, 2)],
            expiration_days=30,
            bias="bullish",
        )
    if bearish:
        return StrategySelection(
            name="Long Put",
            strike_prices=[round(price * 0.98, 2)],
            expiration_days=30,
            bias="bearish",
        )
    return StrategySelection(
        name="Credit Put Spread",
        strike_prices=[round(price * 0.97, 2), round(price * 0.92, 2)],
        expiration_days=30,
        bias="neutral",
    )