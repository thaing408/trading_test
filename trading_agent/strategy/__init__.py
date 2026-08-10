"""Options strategy selection + trading style taxonomy + multi-method router."""

from .competition import compete_sleeves, select_strategy_competitive
from .multi_method import (
    MultiMethodConfig,
    ProcessCardWrite,
    TickerMultiEval,
    evaluate_ticker_all_methods,
    evaluate_universe,
    format_multi_method_report,
    passes_export_quality,
    trade_card_fields_from_eval,
    write_process_cards_for_plays,
)
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
    "MultiMethodConfig",
    "ProcessCardWrite",
    "TickerMultiEval",
    "evaluate_ticker_all_methods",
    "evaluate_universe",
    "format_multi_method_report",
    "passes_export_quality",
    "trade_card_fields_from_eval",
    "write_process_cards_for_plays",
]