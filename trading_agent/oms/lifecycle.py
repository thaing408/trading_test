"""Fill lifecycle: submit → open → protected; reconcile with broker positions."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

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


def _broker_status(broker_response: Optional[Dict[str, Any]]) -> str:
    if not broker_response or not isinstance(broker_response, dict):
        return ""
    return str(
        broker_response.get("status")
        or (broker_response.get("orderStatus") or {}).get("status")
        or ""
    ).lower()


def broker_status_is_filled(broker_response: Optional[Dict[str, Any]]) -> bool:
    """True when broker says the order is actually filled (not merely accepted).

    Used to gate Discord green ENTER — Schwab often returns status=submitted on
    place accept even when MARKET will fill seconds later. Prefer reconcile /
    position match for ENTER when this is False.
    """
    status = _broker_status(broker_response)
    if status in ("filled", "partially_filled", "partial fill", "partialfill"):
        return True
    if not broker_response or not isinstance(broker_response, dict):
        return False
    # Explicit fill fields from some MCP / broker shapes
    for key in ("fill_price", "filled_price", "avg_fill_price", "averagePrice"):
        try:
            v = float(broker_response.get(key) or 0)
            if v > 0:
                return True
        except (TypeError, ValueError):
            continue
    filled_qty = broker_response.get("filledQuantity") or broker_response.get("filled_qty")
    try:
        if filled_qty is not None and float(filled_qty) > 0:
            return True
    except (TypeError, ValueError):
        pass
    return False


def broker_fill_confirmed(broker_response: Optional[Dict[str, Any]]) -> bool:
    """True only when broker response looks like a real working/filled order.

    Cancelled / Error 200 / tokenize_failed must NOT open OMS lots (ghost lots
    filled max_open_lots and blocked paper auto for days).

    Note: this includes submitted/working accepts — enough to open an OMS risk
    slot. Discord green ENTER should use ``broker_status_is_filled`` or a
    subsequent position reconcile, not this alone.
    """
    if not broker_response or not isinstance(broker_response, dict):
        return False
    if broker_response.get("error"):
        return False
    status = _broker_status(broker_response)
    if status in (
        "cancelled",
        "canceled",
        "api cancelled",
        "inactive",
        "rejected",
        "failed",
        "error",
    ):
        return False
    if "cancel" in status:
        return False
    # ib_insync often returns Cancelled after Error 200
    msg = str(broker_response.get("message") or "").lower()
    if "no security definition" in msg or "error 200" in msg:
        return False
    if status in ("submitted", "filled", "working", "queued", "accepted", "presubmitted"):
        return True
    # dry_run should not open live risk slots
    if broker_response.get("dry_run") is True:
        return False
    return order_submitted_ok(broker_response) and status not in ("", "dry_run")


def close_lot_as_orphan(
    store: OmsStore,
    lot: OpenLot,
    *,
    reason: str,
) -> OpenLot:
    """Mark lot closed so it no longer counts toward max_open_lots."""
    lot.status = LotStatus.CLOSED.value
    lot.closed_at = datetime.now(timezone.utc).isoformat()
    lot.exit_reason = reason[:200]
    meta = dict(lot.broker_meta or {})
    meta["orphan_close"] = {
        "reason": reason,
        "ts": lot.closed_at,
    }
    lot.broker_meta = meta
    store.upsert_lot(lot)
    append_audit(
        "lot_orphan_closed",
        payload={"lot_id": lot.lot_id, "symbol": lot.symbol, "reason": reason},
    )
    return lot


def register_submitted_lot(
    store: OmsStore,
    lot: OpenLot,
    *,
    broker_response: Optional[Dict[str, Any]] = None,
    fill_entry: Optional[float] = None,
    legs: Optional[List[Dict[str, Any]]] = None,
) -> OpenLot:
    """Mark lot submitted/open and store multi-leg OCC list when present.

    If broker response is cancelled/failed, mark lot FAILED instead of protected
    so max_open_lots is not consumed by ghosts.
    """
    if not broker_fill_confirmed(broker_response):
        lot.status = LotStatus.FAILED.value
        lot.closed_at = datetime.now(timezone.utc).isoformat()
        lot.exit_reason = "broker_not_filled"
        meta = dict(lot.broker_meta or {})
        meta["broker_response"] = broker_response or {}
        lot.broker_meta = meta
        store.upsert_lot(lot)
        append_audit(
            "lot_not_opened",
            payload={
                "lot_id": lot.lot_id,
                "symbol": lot.symbol,
                "broker": broker_response,
            },
        )
        return lot

    lot.status = LotStatus.SUBMITTED.value
    lot.submitted_at = lot.submitted_at or datetime.now(timezone.utc).isoformat()
    meta = dict(lot.broker_meta or {})
    # Green Discord ENTER waits for true fill or position reconcile
    meta["journal_entry_pending"] = not broker_status_is_filled(broker_response)
    if legs:
        # store on broker_meta for exit engine
        meta["legs"] = legs
        lot.broker_meta = meta
        # primary occ = first long leg or first leg
        for leg in legs:
            if str(leg.get("instruction") or "").upper() == "BUY_TO_OPEN":
                lot.occ_symbol = str(leg.get("occ_symbol") or lot.occ_symbol)
                break
        if not lot.occ_symbol and legs:
            lot.occ_symbol = str(legs[0].get("occ_symbol") or "")
    else:
        lot.broker_meta = meta
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
            # Expired option contracts cannot still be open
            exp_raw = str(lot.expiration or "")[:10]
            try:
                if exp_raw and date.fromisoformat(exp_raw) < datetime.now(timezone.utc).date():
                    return close_lot_as_orphan(
                        store, lot, reason=f"expired_option:{exp_raw}_not_at_broker"
                    )
            except ValueError:
                pass
            # Unmatched for > lag: treat as ghost (cancelled never filled)
            lag_min = int(os.getenv("TRADING_AGENT_OMS_ORPHAN_LAG_MIN", "30") or 30)
            opened = str(lot.opened_at or lot.submitted_at or "")
            try:
                if opened:
                    ots = datetime.fromisoformat(opened.replace("Z", "+00:00"))
                    age_min = (datetime.now(timezone.utc) - ots).total_seconds() / 60.0
                    if age_min >= lag_min:
                        return close_lot_as_orphan(
                            store,
                            lot,
                            reason=f"orphan_not_at_broker_age_{int(age_min)}m",
                        )
            except ValueError:
                pass
            meta = dict(lot.broker_meta or {})
            meta["reconcile"] = {"matched": False, "ts": datetime.now(timezone.utc).isoformat()}
            lot.broker_meta = meta
        store.upsert_lot(lot)
        return lot

    avg = position_avg_price(found)
    qty = position_qty(found)
    instr = (lot.instrument or "").lower()
    is_opt = instr in ("options", "option") or len((lot.occ_symbol or "")) >= 15
    if avg > 0:
        if is_opt and avg < 50:
            # True option fill premium — keep structure on lot.entry
            from trading_agent.oms.manage_rules import capture_option_premium

            capture_option_premium(lot, premium=avg, source="broker_avg_reconcile")
            # Only set fill_entry to premium when prior fill looked like und/missing
            if float(lot.fill_entry or 0) <= 0 or float(lot.fill_entry or 0) >= 50:
                pass  # leave und structure in fill_entry if present; premium in meta
        else:
            lot.fill_entry = avg
            if lot.expected_entry:
                lot.slippage = avg - float(lot.expected_entry)
    if qty and abs(qty) >= 1:
        lot.quantity = int(abs(qty))
    was_pending_entry = bool((lot.broker_meta or {}).get("journal_entry_pending"))
    if lot.status in (LotStatus.SUBMITTED.value, LotStatus.PENDING.value):
        lot.status = LotStatus.PROTECTED.value if lot.stop > 0 else LotStatus.OPEN.value
        lot.opened_at = lot.opened_at or datetime.now(timezone.utc).isoformat()
    meta = dict(lot.broker_meta or {})
    meta["reconcile"] = {
        "matched": True,
        "qty": qty,
        "avg": avg,
        "ts": datetime.now(timezone.utc).isoformat(),
        "option_entry_premium": meta.get("option_entry_premium"),
    }
    # Position at broker → safe to post green ENTER (once)
    if was_pending_entry or meta.get("journal_entry_pending"):
        meta["journal_entry_pending"] = False
        meta["journal_entry_due"] = True
    # Persist initial_stop once for trail math
    if "initial_stop" not in meta and lot.stop:
        meta["initial_stop"] = float(lot.stop)
    lot.broker_meta = meta
    store.upsert_lot(lot)
    append_audit(
        "lot_reconciled",
        payload={
            "lot_id": lot.lot_id,
            "symbol": lot.symbol,
            "fill": lot.fill_entry,
            "option_premium": (lot.broker_meta or {}).get("option_entry_premium"),
            "qty": qty,
            "journal_entry_due": bool(meta.get("journal_entry_due")),
        },
    )
    return lot


def _notify_pending_journal_entries(store: OmsStore, *, live: bool = True) -> List[str]:
    """Post fill-confirmed Discord ENTER for lots flagged after reconcile."""
    posted: List[str] = []
    if not live:
        return posted
    try:
        from trading_agent.ops.journal_notify import notify_lot_entry_filled
    except Exception:  # noqa: BLE001
        return posted
    for lot in list(store.open_lots()):
        meta = dict(lot.broker_meta or {})
        if not meta.get("journal_entry_due"):
            continue
        try:
            prem = meta.get("option_entry_premium")
            try:
                prem_f = float(prem) if prem is not None else None
            except (TypeError, ValueError):
                prem_f = None
            out = notify_lot_entry_filled(lot, live=True, fill_price=prem_f)
            meta["journal_entry_due"] = False
            meta["journal_entry_pending"] = False
            meta["journal_entry_posted"] = True
            lot.broker_meta = meta
            store.upsert_lot(lot)
            if out.get("ok") or out.get("skipped"):
                posted.append(lot.lot_id)
            append_audit(
                "journal_entry_from_reconcile",
                payload={
                    "lot_id": lot.lot_id,
                    "symbol": lot.symbol,
                    "result": {k: out.get(k) for k in ("ok", "skipped", "reason", "error") if k in out},
                },
            )
        except Exception as exc:  # noqa: BLE001 — fail-open
            append_audit(
                "journal_entry_from_reconcile_error",
                payload={"lot_id": lot.lot_id, "error": str(exc)},
            )
    return posted


def reconcile_open_lots(store: OmsStore, call_mcp: McpCaller) -> Dict[str, Any]:
    """Pull broker positions and reconcile all open OMS lots."""
    resp = fetch_positions(call_mcp)
    if resp.get("error"):
        append_audit("reconcile_failed", payload=resp)
        return {"ok": False, "error": resp.get("error"), "lots": []}

    idx = index_positions_by_symbol(resp)
    updated = []
    closed: List[str] = []
    for lot in list(store.open_lots()):
        before = lot.status
        reconcile_lot_with_positions(store, lot, idx)
        after = store.get_lot(lot.lot_id)
        updated.append(lot.lot_id)
        if after and after.status == LotStatus.CLOSED.value and before != LotStatus.CLOSED.value:
            closed.append(lot.lot_id)
    entry_posts = _notify_pending_journal_entries(store, live=True)
    store.save()
    return {
        "ok": True,
        "reconciled": updated,
        "closed_orphans": closed,
        "journal_entries_posted": entry_posts,
        "broker_symbols": list(idx.keys())[:50],
    }


def prune_ghost_lots_ibkr(store: OmsStore) -> Dict[str, Any]:
    """Close OMS open lots that are not in IBKR portfolio (paper me-ai).

    Uses ib_insync portfolio when TRADING_AGENT_BROKER=ibkr / IBKR_ENABLED.
    """
    broker = (os.getenv("TRADING_AGENT_BROKER") or "").strip().lower()
    ibkr_on = (os.getenv("IBKR_ENABLED") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if broker not in ("ibkr", "ib") and not ibkr_on:
        return {"ok": False, "error": "not_ibkr", "closed": []}

    symbols: Set[str] = set()
    try:
        from trading_agent.discord.paper_activity import fetch_ibkr_positions

        rows = fetch_ibkr_positions() or []
        for r in rows:
            for k in ("symbol", "localSymbol"):
                s = str(r.get(k) or "").upper().strip()
                if s:
                    symbols.add(s)
                    # also bare root for "SPY" vs option codes
                    symbols.add(s.split()[0])
    except Exception as exc:  # noqa: BLE001
        append_audit("prune_ibkr_failed", payload={"error": str(exc)})
        return {"ok": False, "error": str(exc), "closed": []}

    closed: List[str] = []
    today = datetime.now(timezone.utc).date()
    for lot in list(store.open_lots()):
        exp_raw = str(lot.expiration or "")[:10]
        try:
            if exp_raw and date.fromisoformat(exp_raw) < today:
                close_lot_as_orphan(store, lot, reason=f"expired:{exp_raw}")
                closed.append(lot.lot_id)
                continue
        except ValueError:
            pass
        keys = {lot.symbol.upper()}
        if lot.occ_symbol:
            keys.add(lot.occ_symbol.upper())
            keys.add(lot.occ_symbol.upper().split()[0])
        if keys & symbols:
            continue
        # not at broker
        close_lot_as_orphan(
            store,
            lot,
            reason="ghost_not_in_ibkr_portfolio",
        )
        closed.append(lot.lot_id)
    store.save()
    append_audit(
        "prune_ghost_lots_ibkr",
        payload={"closed": closed, "broker_symbols": sorted(symbols)[:40]},
    )
    return {"ok": True, "closed": closed, "broker_symbols": sorted(symbols)[:40]}


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
