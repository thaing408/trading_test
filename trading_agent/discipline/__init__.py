"""Book-informed auto-trade discipline (Douglas, Steenbarger, Shannon, Bellafiore)."""

from trading_agent.discipline.edge import (
    EdgePackage,
    EdgeValidation,
    edge_from_opportunity_fields,
    validate_edge_package,
)
from trading_agent.discipline.mtf_gate import (
    MtfGateResult,
    apply_mtf_gate,
    higher_timeframe_bias,
    is_a_tier_mtf_eligible,
)
from trading_agent.discipline.playbook import (
    PLAYBOOK_CATALOG,
    ChecklistResult,
    PlaybookSetup,
    evaluate_checklist,
    list_setup_ids,
    match_playbook,
    require_playbook_pass,
)
from trading_agent.discipline.process import (
    ProcessScore,
    process_from_trade_row,
    process_insights_from_trades,
    score_process,
    setup_attribution_stats,
)
from trading_agent.discipline.rails import (
    RailDecision,
    SessionRiskState,
    check_discipline_rails,
    symbol_in_cooldown,
)

__all__ = [
    "PLAYBOOK_CATALOG",
    "ChecklistResult",
    "EdgePackage",
    "EdgeValidation",
    "MtfGateResult",
    "PlaybookSetup",
    "ProcessScore",
    "RailDecision",
    "SessionRiskState",
    "apply_mtf_gate",
    "check_discipline_rails",
    "edge_from_opportunity_fields",
    "evaluate_checklist",
    "higher_timeframe_bias",
    "is_a_tier_mtf_eligible",
    "list_setup_ids",
    "match_playbook",
    "process_from_trade_row",
    "process_insights_from_trades",
    "require_playbook_pass",
    "score_process",
    "setup_attribution_stats",
    "symbol_in_cooldown",
    "validate_edge_package",
]
