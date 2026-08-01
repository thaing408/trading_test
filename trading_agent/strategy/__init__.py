"""Options strategy selection + trading style taxonomy."""

from .competition import compete_sleeves, select_strategy_competitive
from .selector import select_strategy
from .style import (
    TradingStyle,
    classify_level_signal,
    format_style_brief,
    parse_trading_style,
    style_profile,
)

__all__ = [
    "select_strategy",
    "compete_sleeves",
    "select_strategy_competitive",
    "TradingStyle",
    "classify_level_signal",
    "format_style_brief",
    "parse_trading_style",
    "style_profile",
]