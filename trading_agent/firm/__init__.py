"""Optional TradingAgents-style firm sleeve (arXiv 2412.20138).

P0: schemas/roles/persistence · P1: four analysts · P2: bull/bear debate.
Feature flag: TRADING_AGENT_FIRM=0 (default off) — CIO/OMS unchanged.
"""

from trading_agent.firm.runner import (
    maybe_run_firm_after_research,
    run_firm_for_symbol,
    run_firm_sleeve,
)
from trading_agent.firm.state import firm_enabled, firm_symbol_dir

__all__ = [
    "firm_enabled",
    "firm_symbol_dir",
    "maybe_run_firm_after_research",
    "run_firm_for_symbol",
    "run_firm_sleeve",
]
