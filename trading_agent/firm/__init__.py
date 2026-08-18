"""Optional TradingAgents-style firm sleeve (arXiv 2412.20138).

P0–P3: schemas · analysts · debate · trader proposal (+ optional book merge).
Feature flag: TRADING_AGENT_FIRM=0 (default off) — CIO/OMS unchanged.
"""

from trading_agent.firm.runner import (
    maybe_run_firm_after_research,
    run_firm_for_symbol,
    run_firm_sleeve,
)
from trading_agent.firm.state import firm_enabled, firm_symbol_dir
from trading_agent.firm.trader import book_merge_enabled, proposal_to_book_fields

__all__ = [
    "book_merge_enabled",
    "firm_enabled",
    "firm_symbol_dir",
    "maybe_run_firm_after_research",
    "proposal_to_book_fields",
    "run_firm_for_symbol",
    "run_firm_sleeve",
]
