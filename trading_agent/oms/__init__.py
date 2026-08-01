"""Order management system for macOS auto-trade (fail-closed by default).

Provides:
- Durable order/lot state (idempotent consume)
- JSONL audit trail
- Kill switch / day-loss halt
- Pre-trade gates (heat, max open, quote freshness hooks)
- Post-fill protect + software exit loop
- Multi-leg / credit ready specs (live multi-leg still fail-closed unless enabled)
"""

from trading_agent.oms.audit import append_audit, audit_path
from trading_agent.oms.exits import flatten_all_lots, manage_open_lots
from trading_agent.oms.kill_switch import (
    clear_kill_switch,
    is_killed,
    kill_switch_status,
    set_kill_switch,
)
from trading_agent.oms.lifecycle import reconcile_open_lots, register_submitted_lot
from trading_agent.oms.multileg import multileg_live_allowed
from trading_agent.oms.state import LotStatus, OpenLot, OmsStore

__all__ = [
    "OmsStore",
    "OpenLot",
    "LotStatus",
    "append_audit",
    "audit_path",
    "is_killed",
    "set_kill_switch",
    "clear_kill_switch",
    "kill_switch_status",
    "manage_open_lots",
    "flatten_all_lots",
    "reconcile_open_lots",
    "register_submitted_lot",
    "multileg_live_allowed",
]
