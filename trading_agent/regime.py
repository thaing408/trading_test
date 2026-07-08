"""Market regime inference from bias text."""


def infer_market_regime(bias: str) -> str:
    lower = bias.lower()
    if "bearish" in lower:
        return "bearish"
    if "bullish" in lower:
        return "bullish"
    return "neutral"