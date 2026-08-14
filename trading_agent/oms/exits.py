"""Exit / manage loop: close open lots via Schwab MCP when rules fire."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from trading_agent.journal.trades import JournalTrade, append_journal_trade
from trading_agent.oms.audit import append_audit
from trading_agent.oms.broker import (
    close_instruction_for_open_leg,
    flatten_symbols,
    order_submitted_ok,
    place_equity,
    place_option,
)
from trading_agent.oms.kill_switch import should_flatten
from trading_agent.oms.protect import should_exit_lot
from trading_agent.oms.state import LotStatus, OpenLot, OmsStore


McpCaller = Callable[[str, Dict[str, Any]], Dict[str, Any]]


def _close_instruction(lot: OpenLot) -> str:
    instr = (lot.instrument or "").lower()
    if instr in ("options", "option"):
        path = (lot.place_path or "").lower()
        strat = (lot.strategy or "").lower()
        if "credit" in path or "credit" in strat or "short" in (lot.side or "").lower():
            if "debit" not in strat:
                return "BUY_TO_CLOSE"
        return "SELL_TO_CLOSE"
    return "SELL"


def _legs_for_lot(lot: OpenLot) -> List[Dict[str, Any]]:
    legs = (lot.broker_meta or {}).get("legs") or []
    if isinstance(legs, list) and legs:
        return [leg for leg in legs if isinstance(leg, dict)]
    pkg = (lot.broker_meta or {}).get("multileg_package") or {}
    if isinstance(pkg, dict):
        return [leg for leg in (pkg.get("legs") or []) if isinstance(leg, dict)]
    # also check nested place responses
    for item in (lot.broker_meta or {}).get("responses") or []:
        if isinstance(item, dict) and isinstance(item.get("leg"), dict):
            legs.append(item["leg"])
    return [leg for leg in legs if isinstance(leg, dict)]


def submit_close(
    lot: OpenLot,
    *,
    live: bool,
    call_mcp: McpCaller,
    reason: str,
) -> Dict[str, Any]:
    """Submit close for a lot. Multi-leg closes each OCC with inverse instruction."""
    qty = max(1, int(lot.quantity or 1))
    instrument = (lot.instrument or "").lower()
    legs = _legs_for_lot(lot)

    if instrument in ("options", "option") and len(legs) >= 2:
        responses = []
        all_ok = True
        for leg in legs:
            occ = str(leg.get("occ_symbol") or "")
            if not occ:
                continue
            open_i = str(leg.get("instruction") or "BUY_TO_OPEN")
            close_i = close_instruction_for_open_leg(open_i)
            lqty = int(leg.get("quantity") or qty)
            resp = place_option(
                call_mcp,
                occ=occ,
                quantity=lqty,
                instruction=close_i,
                live=live,
            )
            responses.append({"occ": occ, "instruction": close_i, "response": resp})
            if not order_submitted_ok(resp):
                all_ok = False
        return {
            "mode": "multileg_close",
            "status": "submitted" if all_ok and live else ("dry_run" if not live else "partial"),
            "dry_run": not live,
            "reason": reason,
            "responses": responses,
            "error": None if all_ok else "partial_multileg_close",
        }

    if instrument in ("options", "option"):
        symbol = (lot.occ_symbol or "").strip()
        if not symbol:
            return {
                "error": "missing_occ",
                "mode": "ready_only",
                "message": "No OCC on lot — close multi-leg in TOS",
                "reason": reason,
            }
        return place_option(
            call_mcp,
            occ=symbol,
            quantity=qty,
            instruction=_close_instruction(lot),
            live=live,
        )

    return place_equity(
        call_mcp,
        symbol=lot.symbol,
        quantity=qty,
        instruction="SELL",
        live=live,
    )


def close_lot(
    store: OmsStore,
    lot: OpenLot,
    *,
    live: bool,
    call_mcp: McpCaller,
    reason: str,
    exit_price: float = 0.0,
    journal: bool = True,
) -> OpenLot:
    lot.status = LotStatus.EXITING.value
    store.upsert_lot(lot)
    resp = submit_close(lot, live=live, call_mcp=call_mcp, reason=reason)
    lot.broker_meta = {**(lot.broker_meta or {}), "close": resp}

    ok = not resp.get("error")
    status = str(resp.get("status") or "").lower()
    if live and ok and (status == "submitted" or resp.get("dry_run") is False):
        lot.status = LotStatus.CLOSED.value
        lot.closed_at = datetime.now(timezone.utc).isoformat()
        lot.exit_reason = reason
        lot.exit_price = float(exit_price or lot.fill_entry or lot.entry or 0)
        # crude P/L proxy for equity; options use max_risk scale if needed
        entry = float(lot.fill_entry or lot.entry or 0)
        exit_px = float(lot.exit_price or 0)
        pnl = 0.0
        if entry and exit_px and (lot.instrument or "").lower() in ("equity", "underlying", "etf", "stock"):
            pnl = (exit_px - entry) * int(lot.quantity or 0)
        store.add_realized_pnl(pnl)
        try:
            trips = store.record_round_trip(lot.symbol)
        except Exception:
            trips = 0
        if journal:
            _journal_close(lot, pnl=pnl)
        append_audit(
            "lot_closed",
            payload={
                "lot_id": lot.lot_id,
                "symbol": lot.symbol,
                "reason": reason,
                "pnl": pnl,
                "symbol_round_trips_today": trips,
            },
        )
    elif not live:
        lot.status = LotStatus.EXITING.value
        lot.exit_reason = reason
        lot.broker_meta["close_mode"] = "dry_run"
        append_audit(
            "lot_close_dry_run",
            payload={"lot_id": lot.lot_id, "symbol": lot.symbol, "reason": reason},
        )
    else:
        lot.status = LotStatus.PROTECTED.value if lot.stop else LotStatus.OPEN.value
        append_audit(
            "lot_close_failed",
            payload={"lot_id": lot.lot_id, "symbol": lot.symbol, "resp": resp},
        )
    store.upsert_lot(lot)
    return lot


def _journal_close(lot: OpenLot, *, pnl: float) -> None:
    append_journal_trade(
        JournalTrade(
            symbol=lot.symbol,
            entry=float(lot.fill_entry or lot.entry or 0),
            exit=float(lot.exit_price or 0),
            profit_loss=pnl,
            strategy=lot.strategy,
            setup_id=lot.setup_id,
            direction=lot.side,
            stop_loss=float(lot.stop or 0),
            profit_target=float(lot.target or 0),
            exit_reason=lot.exit_reason,
            entry_time=lot.opened_at,
            exit_time=lot.closed_at,
            notes=f"oms lot={lot.lot_id} slip={lot.slippage:.4f} path={lot.place_path}",
            expected_entry=float(lot.expected_entry or lot.entry or 0),
            fill_entry=float(lot.fill_entry or 0),
            slippage=float(lot.slippage or 0),
            lot_id=lot.lot_id,
            place_path=lot.place_path,
        )
    )


def flatten_all_lots(
    store: OmsStore,
    *,
    live: bool,
    call_mcp: McpCaller,
    also_broker_account: bool = True,
) -> Dict[str, Any]:
    """Close every OMS open lot; optionally also flatten matching broker positions."""
    results = []
    for lot in list(store.open_lots()):
        close_lot(
            store,
            lot,
            live=live,
            call_mcp=call_mcp,
            reason="flatten_all",
        )
        results.append({"lot_id": lot.lot_id, "status": lot.status})
    broker = {}
    if also_broker_account:
        # Flatten OMS symbols + full account sweep when kill flatten is requested
        syms = list({lot.symbol for lot in store.all_lots() if lot.status != LotStatus.CLOSED.value})
        broker = flatten_symbols(call_mcp, live=live, symbols=syms or None)
    store.save()
    append_audit(
        "flatten_all",
        payload={"live": live, "lots": len(results), "broker_ok": broker.get("ok")},
    )
    return {"lots": results, "broker": broker}


def manage_open_lots(
    store: OmsStore,
    *,
    live: bool,
    call_mcp: McpCaller,
    marks: Optional[Dict[str, float]] = None,
    underlying_marks: Optional[Dict[str, float]] = None,
    reconcile_first: bool = True,
) -> List[Dict[str, Any]]:
    """Evaluate open lots for stop/target or flatten kill."""
    marks = marks or {}
    underlying_marks = underlying_marks or {}
    results: List[Dict[str, Any]] = []

    if reconcile_first and live:
        try:
            from trading_agent.oms.lifecycle import reconcile_open_lots

            reconcile_open_lots(store, call_mcp)
        except Exception as exc:
            append_audit("reconcile_exception", payload={"error": str(exc)})

    flatten = should_flatten()
    if flatten:
        flat = flatten_all_lots(store, live=live, call_mcp=call_mcp, also_broker_account=True)
        results.append({"action": "flatten_all", "detail": flat})
        return results

    for lot in list(store.open_lots()):
        if lot.status not in (
            LotStatus.OPEN.value,
            LotStatus.PROTECTED.value,
            LotStatus.SUBMITTED.value,
            LotStatus.EXITING.value,
        ):
            continue

        und = underlying_marks.get(lot.symbol.upper())
        mark = marks.get(lot.occ_symbol or lot.symbol.upper(), und or 0.0)
        should, reason = should_exit_lot(lot, mark_price=float(mark or 0), underlying_price=und)

        def _row(action: str, reason_s: str = "") -> Dict[str, Any]:
            strikes = lot.strike_prices or []
            strike_s = ""
            if strikes:
                try:
                    strike_s = "/".join(f"{float(s):g}" for s in strikes[:3])
                except (TypeError, ValueError):
                    strike_s = ",".join(str(s) for s in strikes[:3])
            return {
                "lot_id": lot.lot_id,
                "lot_id_short": (lot.lot_id or "")[-6:],
                "symbol": lot.symbol,
                "action": action,
                "reason": reason_s,
                "status": lot.status,
                "side": lot.side or "",
                "instrument": lot.instrument or "",
                "strategy": lot.strategy or "",
                "setup_id": lot.setup_id or "",
                "quantity": lot.quantity,
                "entry": lot.entry,
                "stop": lot.stop,
                "target": lot.target,
                "expiration": lot.expiration or "",
                "occ_symbol": lot.occ_symbol or "",
                "strikes": strike_s,
                "mark": float(mark or 0) or None,
                "underlying": float(und) if und is not None else None,
            }

        if should:
            close_lot(
                store,
                lot,
                live=live,
                call_mcp=call_mcp,
                reason=reason,
                exit_price=float(und or mark or 0),
            )
            results.append(_row("exit", reason or ""))
        else:
            results.append(_row("hold"))
    store.save()
    return results


def manage_enabled() -> bool:
    return os.getenv("TRADING_AGENT_OMS_MANAGE", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
