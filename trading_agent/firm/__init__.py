"""Optional TradingAgents-style firm sleeve (arXiv 2412.20138).

P0–P7 firm sleeve: analysts · debate · trader · risk/manager · eval · Discord card.
Feature flag: TRADING_AGENT_FIRM=0 (default off) — CIO/OMS unchanged.
"""

from trading_agent.firm.eval import evaluate_firm_day
from trading_agent.firm.runner import (
    maybe_run_firm_after_research,
    run_firm_for_symbol,
    run_firm_sleeve,
)
from trading_agent.firm.state import firm_enabled, firm_symbol_dir
from trading_agent.firm.trader import book_merge_enabled, proposal_to_book_fields

__all__ = [
    "book_merge_enabled",
    "evaluate_firm_day",
    "firm_enabled",
    "firm_symbol_dir",
    "maybe_run_firm_after_research",
    "proposal_to_book_fields",
    "run_firm_for_symbol",
    "run_firm_sleeve",
]
