"""Fill lifecycle: submit → open → protected; reconcile with broker positions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from trading_agent.oms.audit import append_audit
from trading_agent.oms.broker import (
    fetch_positions,
    index_positions_by_symbol,
    order_submitted_ok,
    position_avg_price,
    position_qty,
)
from trading_agent.oms.protect import mark_lot_open_from_submit
from trading_agent.oms.state import LotStatus, OpenLot, OmsStore

McpCaller = Callable[[str, Dict[str, Any]], Dict[str, Any]]


def register_submitted_lot(
    store: OmsStore,
    lot: OpenLot,
    *,
    broker_response: Optional[Dict[str, Any]] = None,
    fill_entry: Optional[float] = None,
    legs: Optional[List[Dict[str, Any]]] = None,
) -> OpenLot:
    """Mark lot submitted/open and store multi-leg OCC list when present."""
    lot.status = LotStatus.SUBMITTED.value
    lot.submitted_at = lot.submitted_at or datetime.now(timezone.utc).isoformat()
    if legs:
        # store on broker_meta for exit engine
        meta = dict(lot.broker_meta or {})
        meta["legs"] = legs
        lot.broker_meta = meta
        # primary occ = first long leg or first leg
        for leg in legs:
            if str(leg.get("instruction") or "").upper() == "BUY_TO_OPEN":
                lot.occ_symbol = str(leg.get("occ_symbol") or lot.occ_symbol)
                break
        if not lot.occ_symbol and legs:
            lot.occ_symbol = str(legs[0].get("occ_symbol") or "")
    return mark_lot_open_from_submit(
        store,
        lot,
        broker_response=broker_response,
        fill_entry=fill_entry,
    )


def reconcile_lot_with_positions(
    store: OmsStore,
    lot: OpenLot,
    pos_index: Dict[str, Dict[str, Any]],
) -> OpenLot:
    """Update fill from broker position if found; flag orphan if missing when OPEN."""
    keys = []
    if lot.occ_symbol:
        keys.append(lot.occ_symbol.upper())
    keys.append(lot.symbol.upper())
    for leg in (lot.broker_meta or {}).get("legs") or []:
        if isinstance(leg, dict) and leg.get("occ_symbol"):
            keys.append(str(leg["occ_symbol"]).upper())

    found = None
    for k in keys:
        if k in pos_index:
            found = pos_index[k]
            break

    if found is None:
        if lot.status in (LotStatus.OPEN.value, LotStatus.PROTECTED.value, LotStatus.SUBMITTED.value):
            # leave open; note reconcile miss (may be settlement lag)
            meta = dict(lot.broker_meta or {})
            meta["reconcile"] = {"matched": False, "ts": datetime.now(timezone.utc).isoformat()}
            lot.broker_meta = meta
        store.upsert_lot(lot)
        return lot

    avg = position_avg_price(found)
    qty = position_qty(found)
    if avg > 0:
        lot.fill_entry = avg
        if lot.expected_entry:
            lot.slippage = avg - float(lot.expected_entry)
    if qty and abs(qty) >= 1:
        lot.quantity = int(abs(qty))
    if lot.status in (LotStatus.SUBMITTED.value, LotStatus.PENDING.value):
        lot.status = LotStatus.PROTECTED.value if lot.stop > 0 else LotStatus.OPEN.value
        lot.opened_at = lot.opened_at or datetime.now(timezone.utc).isoformat()
    meta = dict(lot.broker_meta or {})
    meta["reconcile"] = {
        "matched": True,
        "qty": qty,
        "avg": avg,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    lot.broker_meta = meta
    store.upsert_lot(lot)
    append_audit(
        "lot_reconciled",
        payload={"lot_id": lot.lot_id, "symbol": lot.symbol, "fill": lot.fill_entry, "qty": qty},
    )
    return lot


def reconcile_open_lots(store: OmsStore, call_mcp: McpCaller) -> Dict[str, Any]:
    """Pull broker positions and reconcile all open OMS lots."""
    resp = fetch_positions(call_mcp)
    if resp.get("error"):
        append_audit("reconcile_failed", payload=resp)
        return {"ok": False, "error": resp.get("error"), "lots": []}

    idx = index_positions_by_symbol(resp)
    updated = []
    for lot in store.open_lots():
        reconcile_lot_with_positions(store, lot, idx)
        updated.append(lot.lot_id)
    store.save()
    return {"ok": True, "reconciled": updated, "broker_symbols": list(idx.keys())[:50]}


def extract_legs_from_broker_response(broker_response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pull leg list from sequential multileg or package responses."""
    legs: List[Dict[str, Any]] = []
    pkg = broker_response.get("multileg_package") or {}
    if isinstance(pkg, dict):
        for leg in pkg.get("legs") or []:
            if isinstance(leg, dict):
                legs.append(leg)
    for item in broker_response.get("responses") or []:
        if not isinstance(item, dict):
            continue
        leg = item.get("leg") or {}
        if isinstance(leg, dict) and leg.get("occ_symbol"):
            legs.append(leg)
    # de-dupe by occ
    seen = set()
    out = []
    for leg in legs:
        occ = str(leg.get("occ_symbol") or "")
        if occ and occ not in seen:
            seen.add(occ)
            out.append(leg)
    return out


def submit_ok(broker_response: Dict[str, Any]) -> bool:
    return order_submitted_ok(broker_response)
