"""Web-informed trading method research (process frameworks + options)."""

from trading_agent.methods.options_methods import (
    OPTIONS_BASELINE_METHODS,
    evaluate_options_methods,
    options_methods_as_dict,
)
from trading_agent.methods.web_methods import (
    BASELINE_METHODS,
    MethodTag,
    evaluate_methods_for_setup,
    format_methods_for_discord,
    methods_as_dict,
    research_trading_methods,
)

__all__ = [
    "BASELINE_METHODS",
    "OPTIONS_BASELINE_METHODS",
    "MethodTag",
    "evaluate_methods_for_setup",
    "evaluate_options_methods",
    "format_methods_for_discord",
    "methods_as_dict",
    "options_methods_as_dict",
    "research_trading_methods",
]
