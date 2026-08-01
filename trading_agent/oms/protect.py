"""Post-fill protective management (software stops until broker OCO available)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from trading_agent.oms.audit import append_audit
from trading_agent.oms.state import LotStatus, OpenLot, OmsStore


def mark_lot_open_from_submit(
    store: OmsStore,
    lot: OpenLot,
    *,
    broker_response: Optional[Dict[str, Any]] = None,
    fill_entry: Optional[float] = None,
) -> OpenLot:
    """Transition submitted → open/protected after broker accept."""
    now = datetime.now(timezone.utc).isoformat()
    lot.status = LotStatus.OPEN.value
    lot.submitted_at = lot.submitted_at or now
    lot.opened_at = now
    lot.expected_entry = lot.entry
    if fill_entry is not None and fill_entry > 0:
        lot.fill_entry = float(fill_entry)
        lot.slippage = float(fill_entry) - float(lot.entry or 0)
    else:
        lot.fill_entry = float(lot.entry or 0)
        lot.slippage = 0.0
    if broker_response:
        lot.broker_meta = {**(lot.broker_meta or {}), **broker_response}
        occ = broker_response.get("occ_symbol")
        if occ:
            lot.occ_symbol = str(occ)
        oid = broker_response.get("order_id") or broker_response.get("orderId")
        if oid:
            lot.broker_order_id = str(oid)
    # Mark protected when stop/target known (software manage loop owns exits)
    if lot.stop > 0 and lot.target > 0:
        lot.status = LotStatus.PROTECTED.value
    store.upsert_lot(lot)
    append_audit(
        "lot_opened",
        payload={
            "lot_id": lot.lot_id,
            "symbol": lot.symbol,
            "status": lot.status,
            "fill_entry": lot.fill_entry,
            "slippage": lot.slippage,
            "occ": lot.occ_symbol,
        },
    )
    return lot


def should_exit_lot(
    lot: OpenLot,
    *,
    mark_price: float,
    underlying_price: Optional[float] = None,
) -> Tuple[bool, str]:
    """Software stop/target check.

    For options packages, prefer underlying_price for directional stops when set;
    else use mark_price vs entry-based thresholds when available.
    """
    if lot.status in (LotStatus.CLOSED.value, LotStatus.FAILED.value, LotStatus.SKIPPED.value):
        return False, ""
    px = float(underlying_price if underlying_price is not None else mark_price)
    if px <= 0:
        return False, ""
    stop = float(lot.stop or 0)
    target = float(lot.target or 0)
    entry = float(lot.entry or 0)
    side = (lot.side or "").lower()
    bullish = side in ("long", "bull", "call", "buy", "bullish")
    bearish = side in ("short", "bear", "put", "sell", "bearish")

    # Neutral / multi-leg: use risk band on underlying if both stop/target
    if not bullish and not bearish:
        if stop > 0 and target > 0:
            lo, hi = min(stop, target), max(stop, target)
            # For IC, stop is often outside range — treat breach of band as exit
            if px >= hi or px <= lo:
                # If entry between stop and target, breach outside is stop
                if entry and lo <= entry <= hi:
                    if px >= hi:
                        return True, "range_high_break"
                    return True, "range_low_break"
        return False, ""

    if bullish:
        if stop > 0 and px <= stop:
            return True, "stop_loss"
        if target > 0 and px >= target:
            return True, "profit_target"
    if bearish:
        if stop > 0 and px >= stop:
            return True, "stop_loss"
        if target > 0 and px <= target:
            return True, "profit_target"
    return False, ""
