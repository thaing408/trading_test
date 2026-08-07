"""QQQ/SPY options playbooks: mean-reversion (Shen/multi-DTE) + breakout (OR continuation)."""

from trading_agent.odte.playbook import (
    OdtePlaybookConfig,
    OdteSessionBrief,
    format_odte_brief,
    run_odte_playbook,
)
from trading_agent.odte.multidte import (
    MultidtePlaybookConfig,
    format_multidte_brief,
    run_multidte_backtest,
)
from trading_agent.odte.breakout import (
    BreakoutPlaybookConfig,
    BreakoutSnapshot,
    compute_breakout_snapshot,
    format_888_ti_card,
    format_breakout_brief,
    run_breakout_backtest,
)
from trading_agent.odte.top_winners import (
    TopWinnersConfig,
    apply_bracket_preset,
    format_top_winners_brief,
    passes_drop_fast_filter,
    run_bracket_ab_backtest,
    run_top_winners_backtest,
    run_top_winners_brief,
)

__all__ = [
    "OdtePlaybookConfig",
    "OdteSessionBrief",
    "format_odte_brief",
    "run_odte_playbook",
    "MultidtePlaybookConfig",
    "format_multidte_brief",
    "run_multidte_backtest",
    "BreakoutPlaybookConfig",
    "BreakoutSnapshot",
    "compute_breakout_snapshot",
    "format_888_ti_card",
    "format_breakout_brief",
    "run_breakout_backtest",
    "TopWinnersConfig",
    "apply_bracket_preset",
    "format_top_winners_brief",
    "passes_drop_fast_filter",
    "run_bracket_ab_backtest",
    "run_top_winners_backtest",
    "run_top_winners_brief",
]
