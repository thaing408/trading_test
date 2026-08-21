"""Scalp research tools (multi-ticker BT + universe card + Soulz PA)."""

from trading_agent.scalp.pulse_halt import (
    format_session_halt_card,
    record_pulse_close,
    sleeve_halted,
)
from trading_agent.scalp.universe_card import format_scalp_universe_card, post_scalp_universe_card
from trading_agent.scalp.soulz_pa import (
    SoulzPaConfig,
    format_soulz_brief,
    render_soulz_backtest,
    run_soulz_backtest,
    run_soulz_brief,
)

__all__ = [
    "format_session_halt_card",
    "record_pulse_close",
    "sleeve_halted",
    "format_scalp_universe_card",
    "post_scalp_universe_card",
    "SoulzPaConfig",
    "format_soulz_brief",
    "render_soulz_backtest",
    "run_soulz_backtest",
    "run_soulz_brief",
]