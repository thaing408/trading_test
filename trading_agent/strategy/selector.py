"""Select appropriate defined options strategy for market conditions.

Strategy set aligned to Trading Research prompt:
Cash Secured Put, Covered Call, Bull Put Credit Spread, Bear Call Credit Spread,
Iron Condor, Debit Spread (call/put), Long Call, Long Put, Calendar Spread,
Diagonal Spread.
"""

from __future__ import annotations

from dataclasses import dataclass

from trading_agent.models import OptionsMetrics, TechnicalAnalysis


@dataclass
class StrategySelection:
    name: str
    strike_prices: list[float]
    expiration_days: int
    bias: str
    direction: str = "Neutral"


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
    aligned = technical.timeframe_alignment
    conflicting = aligned == "conflicting"

    # Calendar / diagonal when term structure / mixed TF favors time spreads
    if conflicting and iv_low:
        return StrategySelection(
            name="Calendar Spread",
            strike_prices=[round(price, 2)],
            expiration_days=45,
            bias="neutral",
            direction="Neutral",
        )
    if conflicting and not iv_high and bullish:
        return StrategySelection(
            name="Diagonal Spread",
            strike_prices=[round(price, 2), round(price * 1.05, 2)],
            expiration_days=45,
            bias="bullish",
            direction="Bullish",
        )

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
            direction="Neutral",
        )
    if iv_high and bullish:
        return StrategySelection(
            name="Covered Call",
            strike_prices=[round(price * 1.05, 2)],
            expiration_days=30,
            bias="bullish",
            direction="Bullish",
        )
    if iv_high and bearish:
        return StrategySelection(
            name="Cash Secured Put",
            strike_prices=[round(price * 0.95, 2)],
            expiration_days=30,
            bias="bearish",
            direction="Bearish",
        )
    if iv_high and bullish is False and bearish is False:
        pass  # fall through

    if bullish and options.iv_rank >= 45:
        return StrategySelection(
            name="Bull Put Credit Spread",
            strike_prices=[round(price * 0.97, 2), round(price * 0.92, 2)],
            expiration_days=30,
            bias="bullish",
            direction="Bullish",
        )
    if bearish and options.iv_rank >= 45:
        return StrategySelection(
            name="Bear Call Credit Spread",
            strike_prices=[round(price * 1.03, 2), round(price * 1.08, 2)],
            expiration_days=30,
            bias="bearish",
            direction="Bearish",
        )
    if iv_low and bullish:
        return StrategySelection(
            name="Debit Spread",
            strike_prices=[round(price, 2), round(price * 1.05, 2)],
            expiration_days=45,
            bias="bullish",
            direction="Bullish",
        )
    if iv_low and bearish:
        return StrategySelection(
            name="Debit Spread",
            strike_prices=[round(price, 2), round(price * 0.95, 2)],
            expiration_days=45,
            bias="bearish",
            direction="Bearish",
        )
    if bullish:
        return StrategySelection(
            name="Long Call",
            strike_prices=[round(price * 1.02, 2)],
            expiration_days=30,
            bias="bullish",
            direction="Bullish",
        )
    if bearish:
        return StrategySelection(
            name="Long Put",
            strike_prices=[round(price * 0.98, 2)],
            expiration_days=30,
            bias="bearish",
            direction="Bearish",
        )
    return StrategySelection(
        name="Bull Put Credit Spread",
        strike_prices=[round(price * 0.97, 2), round(price * 0.92, 2)],
        expiration_days=30,
        bias="neutral",
        direction="Neutral",
    )
