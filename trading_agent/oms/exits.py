"""Exit / manage loop: close open lots via Schwab MCP when rules fire."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from trading_agent.journal.trades import JournalTrade, append_journal_trade
from trading_agent.oms.audit import append_audit
from trading_agent.oms.kill_switch import should_flatten
from trading_agent.oms.protect import should_exit_lot
from trading_agent.oms.state import LotStatus, OpenLot, OmsStore


McpCaller = Callable[[str, Dict[str, Any]], Dict[str, Any]]


def _close_instruction(lot: OpenLot) -> str:
    instr = (lot.instrument or "").lower()
    if instr in ("options", "option"):
        # Debit long → SELL_TO_CLOSE; credit short premium → BUY_TO_CLOSE
        path = (lot.place_path or "").lower()
        if "credit" in path or "short" in (lot.side or "").lower():
            if "debit" not in (lot.strategy or "").lower():
                return "BUY_TO_CLOSE"
        return "SELL_TO_CLOSE"
    return "SELL"


def submit_close(
    lot: OpenLot,
    *,
    live: bool,
    call_mcp: McpCaller,
    reason: str,
) -> Dict[str, Any]:
    """Submit close for a lot. Multi-leg lots without OCC stay ready-only."""
    qty = max(1, int(lot.quantity or 1))
    instrument = (lot.instrument or "").lower()
    dry = not live

    if instrument in ("options", "option"):
        symbol = (lot.occ_symbol or "").strip()
        if not symbol:
            return {
                "error": "missing_occ",
                "mode": "ready_only",
                "message": "No OCC on lot — close multi-leg in TOS",
                "reason": reason,
            }
        payload = {
            "symbol": symbol,
            "quantity": qty,
            "instruction": _close_instruction(lot),
            "asset_type": "OPTION",
            "order_type": "MARKET",
            "duration": "DAY",
            "session": "NORMAL",
            "dry_run": dry,
            "confirm_live": bool(live),
        }
    else:
        payload = {
            "symbol": lot.symbol.upper(),
            "quantity": qty,
            "instruction": "SELL",
            "asset_type": "EQUITY",
            "order_type": "MARKET",
            "duration": "DAY",
            "session": "NORMAL",
            "dry_run": dry,
            "confirm_live": bool(live),
        }
    return call_mcp("place_order", payload)


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
        if journal:
            _journal_close(lot, pnl=pnl)
        append_audit(
            "lot_closed",
            payload={"lot_id": lot.lot_id, "symbol": lot.symbol, "reason": reason, "pnl": pnl},
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


def manage_open_lots(
    store: OmsStore,
    *,
    live: bool,
    call_mcp: McpCaller,
    marks: Optional[Dict[str, float]] = None,
    underlying_marks: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """Evaluate open lots for stop/target or flatten kill."""
    marks = marks or {}
    underlying_marks = underlying_marks or {}
    results: List[Dict[str, Any]] = []
    flatten = should_flatten()

    for lot in list(store.open_lots()):
        if lot.status not in (
            LotStatus.OPEN.value,
            LotStatus.PROTECTED.value,
            LotStatus.SUBMITTED.value,
            LotStatus.EXITING.value,
        ):
            continue
        if flatten:
            close_lot(
                store,
                lot,
                live=live,
                call_mcp=call_mcp,
                reason="kill_switch_flatten",
                exit_price=marks.get(lot.symbol.upper(), 0.0),
            )
            results.append({"lot_id": lot.lot_id, "action": "flatten", "status": lot.status})
            continue

        und = underlying_marks.get(lot.symbol.upper())
        mark = marks.get(lot.occ_symbol or lot.symbol.upper(), und or 0.0)
        should, reason = should_exit_lot(lot, mark_price=float(mark or 0), underlying_price=und)
        if should:
            close_lot(
                store,
                lot,
                live=live,
                call_mcp=call_mcp,
                reason=reason,
                exit_price=float(und or mark or 0),
            )
            results.append({"lot_id": lot.lot_id, "action": "exit", "reason": reason, "status": lot.status})
        else:
            results.append({"lot_id": lot.lot_id, "action": "hold", "status": lot.status})
    store.save()
    return results


def manage_enabled() -> bool:
    return os.getenv("TRADING_AGENT_OMS_MANAGE", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
