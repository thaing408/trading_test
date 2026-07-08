"""Research synthesis across market, calendar, and news inputs."""

from .market_context import (
    MarketContext,
    build_watchlist,
    synthesize_market_context,
)

__all__ = ["MarketContext", "synthesize_market_context", "build_watchlist"]