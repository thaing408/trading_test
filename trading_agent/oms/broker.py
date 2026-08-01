"""Schwab MCP broker helpers for OMS (positions, place, flatten)."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from trading_agent.oms.audit import append_audit

McpCaller = Callable[[str, Dict[str, Any]], Dict[str, Any]]


def fetch_positions(call_mcp: McpCaller) -> Dict[str, Any]:
    """Return raw get_positions response (fail-closed dict with error key)."""
    try:
        resp = call_mcp("get_positions", {})
    except Exception as exc:
        return {"error": "get_positions_exception", "message": str(exc)}
    if not isinstance(resp, dict):
        return {"error": "get_positions_bad_shape", "raw": str(resp)[:200]}
    return resp


def positions_list(resp: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize positions payload into a list of dict rows."""
    if resp.get("error"):
        return []
    for key in ("positions", "securitiesAccount", "data", "items"):
        block = resp.get(key)
        if isinstance(block, list):
            return [p for p in block if isinstance(p, dict)]
        if isinstance(block, dict):
            # nested account positions
            for k2 in ("positions", "equities", "options"):
                if isinstance(block.get(k2), list):
                    return [p for p in block[k2] if isinstance(p, dict)]
    # flat list-like values
    if isinstance(resp.get("symbol"), str):
        return [resp]
    return []


def position_symbol(row: Dict[str, Any]) -> str:
    for k in ("symbol", "instrumentSymbol", "occSymbol", "ticker"):
        v = row.get(k)
        if v:
            return str(v).upper().strip()
    inst = row.get("instrument") or {}
    if isinstance(inst, dict):
        for k in ("symbol", "symbolDescription"):
            if inst.get(k):
                return str(inst[k]).upper().strip()
    return ""


def position_qty(row: Dict[str, Any]) -> float:
    for k in ("longQuantity", "quantity", "qty", "shortQuantity"):
        if row.get(k) is not None:
            try:
                return float(row[k])
            except (TypeError, ValueError):
                pass
    return 0.0


def position_avg_price(row: Dict[str, Any]) -> float:
    for k in ("averagePrice", "averageLongPrice", "avgPrice", "costBasis"):
        if row.get(k) is not None:
            try:
                return float(row[k])
            except (TypeError, ValueError):
                pass
    return 0.0


def index_positions_by_symbol(resp: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in positions_list(resp):
        sym = position_symbol(row)
        if not sym:
            continue
        out[sym] = row
    return out


def place_option(
    call_mcp: McpCaller,
    *,
    occ: str,
    quantity: int,
    instruction: str,
    live: bool,
    order_type: str = "MARKET",
    price: Optional[float] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "symbol": occ,
        "quantity": max(1, int(quantity)),
        "instruction": instruction,
        "asset_type": "OPTION",
        "order_type": order_type,
        "duration": "DAY",
        "session": "NORMAL",
        "dry_run": not live,
        "confirm_live": bool(live),
    }
    if order_type == "LIMIT" and price is not None:
        payload["price"] = float(price)
    return call_mcp("place_order", payload)


def place_equity(
    call_mcp: McpCaller,
    *,
    symbol: str,
    quantity: int,
    instruction: str,
    live: bool,
) -> Dict[str, Any]:
    return call_mcp(
        "place_order",
        {
            "symbol": symbol.upper(),
            "quantity": max(1, int(quantity)),
            "instruction": instruction,
            "asset_type": "EQUITY",
            "order_type": "MARKET",
            "duration": "DAY",
            "session": "NORMAL",
            "dry_run": not live,
            "confirm_live": bool(live),
        },
    )


def order_submitted_ok(resp: Dict[str, Any]) -> bool:
    if not resp or resp.get("error"):
        return False
    status = str(resp.get("status") or "").lower()
    if status in ("submitted", "filled", "working", "queued", "accepted"):
        return True
    if resp.get("dry_run") is False and not resp.get("error"):
        return True
    # dry_run path: treat as ok for non-live
    if resp.get("dry_run") is True or status == "dry_run":
        return True
    if resp.get("order_spec") and not resp.get("error"):
        return True
    return False


def close_instruction_for_open_leg(open_instruction: str) -> str:
    """Map open instruction to close instruction."""
    m = {
        "BUY_TO_OPEN": "SELL_TO_CLOSE",
        "SELL_TO_OPEN": "BUY_TO_CLOSE",
        "BUY": "SELL",
        "SELL": "BUY",
    }
    return m.get(open_instruction.upper(), "SELL_TO_CLOSE")


def flatten_symbols(
    call_mcp: McpCaller,
    *,
    live: bool,
    symbols: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Best-effort close of positions (all or filter by symbol/OCC).

    For each long option qty → SELL_TO_CLOSE; short option → BUY_TO_CLOSE;
    long equity → SELL.
    """
    resp = fetch_positions(call_mcp)
    if resp.get("error"):
        append_audit("flatten_failed", payload=resp)
        return {"ok": False, "error": resp.get("error"), "responses": []}

    rows = positions_list(resp)
    want = {s.upper() for s in (symbols or [])} if symbols else None
    closes: List[Dict[str, Any]] = []

    for row in rows:
        sym = position_symbol(row)
        qty = position_qty(row)
        if not sym or abs(qty) < 1e-9:
            continue
        if want is not None:
            # match underlying or full OCC
            under = sym[:6].strip() if len(sym) > 6 else sym
            if sym not in want and under not in want:
                # also allow prefix match for OCC root
                if not any(sym.startswith(w[:6].ljust(6)[:6]) or w in sym for w in want):
                    continue

        short_q = 0.0
        try:
            short_q = float(row.get("shortQuantity") or 0)
        except (TypeError, ValueError):
            short_q = 0.0
        long_q = abs(qty) if short_q <= 0 else float(row.get("longQuantity") or max(qty, 0))

        # Heuristic: OCC-like symbols are options (length/format)
        is_option = len(sym) >= 15 or any(c in sym for c in ("C", "P")) and len(sym) > 8

        if is_option:
            if long_q > 0:
                r = place_option(
                    call_mcp,
                    occ=sym,
                    quantity=int(max(1, long_q)),
                    instruction="SELL_TO_CLOSE",
                    live=live,
                )
                closes.append({"symbol": sym, "instruction": "SELL_TO_CLOSE", "response": r})
            if short_q > 0:
                r = place_option(
                    call_mcp,
                    occ=sym,
                    quantity=int(max(1, short_q)),
                    instruction="BUY_TO_CLOSE",
                    live=live,
                )
                closes.append({"symbol": sym, "instruction": "BUY_TO_CLOSE", "response": r})
        else:
            if qty > 0:
                r = place_equity(
                    call_mcp,
                    symbol=sym,
                    quantity=int(max(1, qty)),
                    instruction="SELL",
                    live=live,
                )
                closes.append({"symbol": sym, "instruction": "SELL", "response": r})

    append_audit(
        "flatten_ran",
        payload={"live": live, "n_closes": len(closes), "filter": list(want or [])},
    )
    return {"ok": True, "responses": closes, "position_count": len(rows)}
