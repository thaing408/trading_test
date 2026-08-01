"""Pre-trade risk gates before broker submit."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from trading_agent.oms.kill_switch import is_killed, kill_switch_status
from trading_agent.oms.state import OmsStore


@dataclass
class PretradeConfig:
    max_open_lots: int = 5
    max_open_risk_dollars: float = 1500.0
    max_day_loss_dollars: float = 500.0
    max_orders_per_consume: int = 3
    max_symbol_lots: int = 1
    require_defined_risk: bool = True
    # quote age seconds; 0 disables
    max_quote_age_seconds: float = 0.0
    # optional buying-power floor (0 = disabled); LIVE path may pass live_bp
    min_buying_power: float = 0.0

    @classmethod
    def from_env(cls) -> "PretradeConfig":
        def _f(name: str, default: float) -> float:
            try:
                return float(os.getenv(name, str(default)))
            except ValueError:
                return default

        def _i(name: str, default: int) -> int:
            try:
                return int(os.getenv(name, str(default)))
            except ValueError:
                return default

        return cls(
            max_open_lots=_i("TRADING_AGENT_MAX_OPEN_LOTS", 5),
            max_open_risk_dollars=_f("TRADING_AGENT_MAX_OPEN_RISK", 1500.0),
            max_day_loss_dollars=_f("TRADING_AGENT_MAX_DAY_LOSS", 500.0),
            max_orders_per_consume=_i("TRADING_AGENT_MAX_ORDERS_PER_CONSUME", 3),
            max_symbol_lots=_i("TRADING_AGENT_MAX_SYMBOL_LOTS", 1),
            require_defined_risk=os.getenv("TRADING_AGENT_REQUIRE_DEFINED_RISK", "1")
            .strip()
            .lower()
            not in ("0", "false", "no"),
            max_quote_age_seconds=_f("TRADING_AGENT_MAX_QUOTE_AGE_SEC", 0.0),
            min_buying_power=_f("TRADING_AGENT_MIN_BUYING_POWER", 0.0),
        )


def evaluate_pretrade(
    order: Any,
    store: OmsStore,
    *,
    config: Optional[PretradeConfig] = None,
    submitted_this_run: int = 0,
    quote_age_seconds: Optional[float] = None,
    buying_power: Optional[float] = None,
) -> Tuple[bool, str]:
    """Return (ok, reason). Fail-closed on kill switch / day loss / heat."""
    cfg = config or PretradeConfig.from_env()

    if is_killed():
        st = kill_switch_status()
        reason = ((st.get("file") or {}) or {}).get("reason") if isinstance(st.get("file"), dict) else ""
        return False, f"kill_switch:{reason or 'active'}"

    if store.day_realized_pnl() <= -abs(cfg.max_day_loss_dollars):
        return False, "daily_loss_halt"

    if store.open_count() >= cfg.max_open_lots:
        return False, "max_open_lots"

    risk = float(getattr(order, "max_risk_dollars", 0) or 0)
    if store.open_risk_dollars() + risk > cfg.max_open_risk_dollars:
        return False, "max_open_risk"

    if submitted_this_run >= cfg.max_orders_per_consume:
        return False, "max_orders_per_consume"

    sym = str(getattr(order, "symbol", "") or "").upper()
    if sym:
        n_sym = sum(1 for lot in store.open_lots() if lot.symbol.upper() == sym)
        if n_sym >= cfg.max_symbol_lots:
            return False, "max_symbol_lots"

    if cfg.require_defined_risk and getattr(order, "instrument", "").lower() in (
        "options",
        "option",
    ):
        if getattr(order, "defined_risk", True) is False:
            return False, "not_defined_risk"

    if cfg.max_quote_age_seconds > 0 and quote_age_seconds is not None:
        if quote_age_seconds > cfg.max_quote_age_seconds:
            return False, "stale_quote"

    # Buying power: use live figure when provided; else skip unless floor set and 0 passed
    min_bp = float(cfg.min_buying_power or 0.0)
    if min_bp > 0 and buying_power is not None and buying_power < min_bp:
        return False, "insufficient_buying_power"
    if buying_power is not None and risk > 0 and buying_power < risk:
        return False, "buying_power_below_risk"

    return True, ""


def pretrade_snapshot(store: OmsStore, config: Optional[PretradeConfig] = None) -> Dict[str, Any]:
    cfg = config or PretradeConfig.from_env()
    return {
        "kill_switch": is_killed(),
        "open_lots": store.open_count(),
        "open_risk": store.open_risk_dollars(),
        "day_realized_pnl": store.day_realized_pnl(),
        "limits": {
            "max_open_lots": cfg.max_open_lots,
            "max_open_risk_dollars": cfg.max_open_risk_dollars,
            "max_day_loss_dollars": cfg.max_day_loss_dollars,
            "max_orders_per_consume": cfg.max_orders_per_consume,
        },
    }
