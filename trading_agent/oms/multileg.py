"""Multi-leg / credit order specs + safe sequential LIVE with one-leg protection.

Schwab MCP place_order is single-instrument. Sequential multi-leg is only
enabled when TRADING_AGENT_ALLOW_SEQUENTIAL_MULTILEG=1.

Safety:
- Credit: BUY wings first, then SELL body
- Debit: BUY long first, then SELL short
- On leg failure: immediately reverse any already-opened legs (one-leg protection)
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from trading_agent.export.mac_execute import (
    ReadyOrder,
    format_occ_symbol,
    parse_expiration_date,
)
from trading_agent.oms.audit import append_audit
from trading_agent.oms.broker import (
    close_instruction_for_open_leg,
    order_submitted_ok,
    place_option,
)


@dataclass
class LegSpec:
    occ_symbol: str
    instruction: str  # BUY_TO_OPEN / SELL_TO_OPEN / etc.
    quantity: int
    call_put: str = ""
    strike: float = 0.0
    role: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MultiLegPackage:
    symbol: str
    strategy: str
    setup_id: str
    expiration: str
    legs: List[LegSpec] = field(default_factory=list)
    net_debit_credit: str = ""
    defined_risk: bool = True
    notes: str = ""
    live_capable: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "setup_id": self.setup_id,
            "expiration": self.expiration,
            "legs": [leg.to_dict() for leg in self.legs],
            "net_debit_credit": self.net_debit_credit,
            "defined_risk": self.defined_risk,
            "notes": self.notes,
            "live_capable": self.live_capable,
        }


def sequential_multileg_enabled() -> bool:
    return os.getenv("TRADING_AGENT_ALLOW_SEQUENTIAL_MULTILEG", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def multileg_live_default_on() -> bool:
    """When true, sequential multi-leg is allowed whenever LIVE consume runs.

    Still requires TRADING_AGENT_ALLOW_SEQUENTIAL_MULTILEG=1 OR this flag.
    Safer default remains off unless user opts in.
    """
    return os.getenv("TRADING_AGENT_MULTILEG_LIVE", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def multileg_live_allowed() -> bool:
    return sequential_multileg_enabled() or multileg_live_default_on()


def _round_level(value: float) -> float:
    return round(float(value), 2)


def _cp_from_strike_index(i: int, n: int, strategy: str) -> str:
    s = strategy.lower()
    if "iron" in s or "condor" in s:
        if n >= 4:
            return "PUT" if i < 2 else "CALL"
    if "bull put" in s or "put credit" in s or "put_spread" in s:
        return "PUT"
    if "bear call" in s or "call credit" in s or "call_spread" in s:
        return "CALL"
    if "debit put" in s:
        return "PUT"
    if "debit call" in s:
        return "CALL"
    return "PUT" if i < n / 2 else "CALL"


def _instruction_for_leg(i: int, n: int, strategy: str, net: str) -> str:
    s = strategy.lower()
    if "debit" in s or net == "debit":
        if n == 2:
            return "BUY_TO_OPEN" if i == 0 else "SELL_TO_OPEN"
        return "BUY_TO_OPEN" if i in (1, 2) else "SELL_TO_OPEN"
    if n == 2:
        # credit vertical: short closer, long wing — sorted low→high;
        # for bull put: short higher strike, long lower → SELL on higher index
        return "BUY_TO_OPEN" if i == 0 else "SELL_TO_OPEN"
    if n >= 4:
        return "BUY_TO_OPEN" if i in (0, n - 1) else "SELL_TO_OPEN"
    return "SELL_TO_OPEN"


def classify_net(order: ReadyOrder) -> str:
    blob = " ".join(
        [order.strategy or "", order.setup_id or "", order.side or "", order.notes or ""]
    ).lower()
    if "credit" in blob or "short premium" in blob:
        return "credit"
    if "debit" in blob or "long call" in blob or "long put" in blob:
        return "debit"
    if "iron" in blob or "condor" in blob:
        return "credit"
    return "unknown"


def build_multileg_package(order: ReadyOrder) -> Optional[MultiLegPackage]:
    strikes = list(order.strike_prices or [])
    if len(strikes) < 2:
        return None
    exp = parse_expiration_date(order.expiration)
    if not exp:
        return None
    strikes_sorted = sorted(float(s) for s in strikes)
    net = classify_net(order)
    legs: List[LegSpec] = []
    n = len(strikes_sorted)
    for i, strike in enumerate(strikes_sorted):
        cp = _cp_from_strike_index(i, n, order.strategy or order.setup_id or "")
        instr = _instruction_for_leg(i, n, order.strategy or "", net)
        occ = format_occ_symbol(order.symbol, exp, cp, strike)
        legs.append(
            LegSpec(
                occ_symbol=occ,
                instruction=instr,
                quantity=max(1, int(order.quantity or 1)),
                call_put=cp,
                strike=strike,
                role=f"leg_{i}",
            )
        )
    return MultiLegPackage(
        symbol=order.symbol,
        strategy=order.strategy,
        setup_id=order.setup_id,
        expiration=order.expiration,
        legs=legs,
        net_debit_credit=net,
        defined_risk=bool(order.defined_risk),
        notes="Sequential LIVE uses wing-first + reverse on failure",
        live_capable=multileg_live_allowed(),
    )


def attach_package_to_order(order: ReadyOrder) -> ReadyOrder:
    pkg = build_multileg_package(order)
    if not pkg:
        return order
    meta = dict(order.broker_response or {})
    meta["multileg_package"] = pkg.to_dict()
    meta["mode"] = meta.get("mode") or "ready_only"
    order.broker_response = meta
    return order


def _leg_sort_key_for_open(net: str, leg: LegSpec) -> int:
    """Lower first: protection legs before short premium."""
    instr = leg.instruction.upper()
    if net == "credit":
        return 0 if instr == "BUY_TO_OPEN" else 1
    if net == "debit":
        return 0 if instr == "BUY_TO_OPEN" else 1
    return 0 if instr == "BUY_TO_OPEN" else 1


def _reverse_opened_legs(call_mcp, opened: List[Dict[str, Any]], *, live: bool) -> List[Dict[str, Any]]:
    """One-leg protection: close any legs already opened on failure."""
    revs = []
    for item in reversed(opened):
        leg = item.get("leg") or {}
        occ = str(leg.get("occ_symbol") or "")
        instr = str(leg.get("instruction") or "BUY_TO_OPEN")
        qty = int(leg.get("quantity") or 1)
        if not occ:
            continue
        close_i = close_instruction_for_open_leg(instr)
        resp = place_option(
            call_mcp,
            occ=occ,
            quantity=qty,
            instruction=close_i,
            live=live,
        )
        revs.append({"leg": leg, "close_instruction": close_i, "response": resp})
        append_audit(
            "multileg_leg_reversed",
            payload={"occ": occ, "close": close_i, "ok": order_submitted_ok(resp)},
        )
    return revs


def try_sequential_submit(
    order: ReadyOrder,
    *,
    live: bool,
    call_mcp,
) -> ReadyOrder:
    """Place multi-leg sequentially with wing-first order and reverse on fail."""
    pkg = build_multileg_package(order)
    if not pkg:
        order.status = "ready"
        order.broker_response = {"mode": "ready_only", "message": "not a multi-leg package"}
        return order

    order = attach_package_to_order(order)
    if not live or not multileg_live_allowed():
        order.status = "ready"
        order.broker_response = {
            **(order.broker_response or {}),
            "mode": "ready_only",
            "place_path": "multi_leg_ready",
            "message": (
                "Multi-leg package built; set TRADING_AGENT_MULTILEG_LIVE=1 "
                "(or ALLOW_SEQUENTIAL_MULTILEG=1) with --live to submit wing-first"
            ),
        }
        return order

    legs = sorted(
        list(pkg.legs),
        key=lambda leg: _leg_sort_key_for_open(pkg.net_debit_credit, leg),
    )
    opened: List[Dict[str, Any]] = []
    responses: List[Dict[str, Any]] = []

    for leg in legs:
        resp = place_option(
            call_mcp,
            occ=leg.occ_symbol,
            quantity=leg.quantity,
            instruction=leg.instruction,
            live=True,
        )
        item = {"leg": leg.to_dict(), "response": resp}
        responses.append(item)
        append_audit(
            "multileg_leg_submit",
            payload={
                "occ": leg.occ_symbol,
                "instruction": leg.instruction,
                "ok": order_submitted_ok(resp),
            },
        )
        if not order_submitted_ok(resp) or resp.get("error"):
            # reverse any successful opens
            revs = _reverse_opened_legs(call_mcp, opened, live=True)
            order.status = "failed"
            order.broker_response = {
                "mode": "sequential_multileg",
                "error": "leg_failed",
                "responses": responses,
                "reversals": revs,
                "multileg_package": pkg.to_dict(),
                "message": (
                    "Multi-leg aborted; attempted reverse of opened legs "
                    "(verify TOS if any reverse failed)"
                ),
            }
            return order
        opened.append(item)

    order.status = "submitted"
    order.broker_response = {
        "mode": "sequential_multileg",
        "status": "submitted",
        "responses": responses,
        "multileg_package": pkg.to_dict(),
        "legs_opened": [x["leg"] for x in opened],
        "message": "All legs submitted (wing-first); manage exits via OMS",
    }
    return order
