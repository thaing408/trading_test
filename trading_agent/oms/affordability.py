"""Pre-trade / pre-close cash & buying-power affordability.

Goal: never send LIVE Schwab place_order when the account cannot fund it.

- Debit opens (BUY_TO_OPEN): need option premium dollars (already buffered).
- Credit opens (SELL_TO_OPEN / short premium): need margin/BP cushion — fail closed
  unless defined-risk package risk fits remaining BP.
- Closes: SELL_TO_CLOSE (long) usually frees cash; BUY_TO_CLOSE (short) needs
  buyback premium.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class AffordabilityResult:
    ok: bool
    reason: str
    need: float = 0.0
    have: float = 0.0
    kind: str = ""  # debit_open | credit_open | buy_to_close | sell_to_close | unknown

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "need": self.need,
            "have": self.have,
            "kind": self.kind,
        }


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


def remaining_tradable(account_cash: Optional[Dict[str, Any]]) -> Optional[float]:
    """Best remaining cash/BP figure from fetch_account_balances parse payload."""
    if not account_cash or not isinstance(account_cash, dict):
        return None
    if account_cash.get("fetched") is False and account_cash.get("error"):
        return None
    for key in (
        "remaining_after_submits",
        "tradable_after_reserve",
        "raw_tradable",
        "cash_available",
        "buying_power",
    ):
        v = account_cash.get(key)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return None


def credit_margin_estimate(
    order: Any,
    *,
    buffer: float = 1.2,
) -> float:
    """Conservative dollars of BP to reserve for short/credit open.

    Prefer package ``max_risk_dollars``. Else rough short-put style floor:
    strike * 100 * qty * 0.20 (Reg-T-ish toy — not a broker calc).
    """
    risk = _f(getattr(order, "max_risk_dollars", 0), 0.0)
    qty = max(1, int(getattr(order, "quantity", 0) or 1))
    if risk > 0:
        return round(risk * max(1.0, float(buffer or 1.0)), 2)
    strikes = list(getattr(order, "strike_prices", None) or [])
    strike = _f(strikes[0] if strikes else 0, 0.0)
    if strike > 0:
        return round(strike * 100.0 * qty * 0.20 * max(1.0, float(buffer or 1.0)), 2)
    entry = _f(getattr(order, "entry", 0), 0.0)
    if entry > 0:
        return round(entry * 100.0 * qty * 0.20 * max(1.0, float(buffer or 1.0)), 2)
    return round(500.0 * qty * max(1.0, float(buffer or 1.0)), 2)


def check_open_affordability(
    order: Any,
    *,
    place_path: str,
    account_cash: Optional[Dict[str, Any]],
    premium_est: Optional[float] = None,
    buffer: float = 1.05,
    require_balances: bool = True,
) -> AffordabilityResult:
    """Gate LIVE opens before place_order."""
    path = (place_path or "").lower()
    have = remaining_tradable(account_cash)

    if path in ("credit_ready",) or "credit" in path:
        kind = "credit_open"
        # Naked / credit: must have balances and enough BP for margin estimate
        if have is None:
            if require_balances:
                return AffordabilityResult(
                    False, "account_cash_unavailable", kind=kind
                )
            return AffordabilityResult(True, "", kind=kind)
        need = credit_margin_estimate(order, buffer=max(buffer, 1.2))
        if have < need:
            return AffordabilityResult(
                False,
                f"insufficient_margin:need={need:.2f}:have={have:.2f}",
                need=need,
                have=have,
                kind=kind,
            )
        # Extra: refuse undefined-risk credits even if BP looks big
        if getattr(order, "defined_risk", True) is False:
            return AffordabilityResult(
                False, "credit_not_defined_risk", need=need, have=have, kind=kind
            )
        return AffordabilityResult(True, "", need=need, have=have, kind=kind)

    # Debit / equity buys
    kind = "debit_open"
    if have is None:
        if require_balances:
            return AffordabilityResult(False, "account_cash_unavailable", kind=kind)
        return AffordabilityResult(True, "", kind=kind)

    if premium_est is not None and premium_est > 0:
        need = float(premium_est)
    else:
        from trading_agent.oms.pretrade import estimate_order_cash_required

        need = estimate_order_cash_required(order, buffer=buffer)

    if need <= 0:
        return AffordabilityResult(True, "", need=0.0, have=have, kind=kind)
    if have < need:
        return AffordabilityResult(
            False,
            f"insufficient_cash:need={need:.2f}:have={have:.2f}",
            need=need,
            have=have,
            kind=kind,
        )
    return AffordabilityResult(True, "", need=need, have=have, kind=kind)


def check_close_affordability(
    lot: Any,
    *,
    instruction: str,
    account_cash: Optional[Dict[str, Any]],
    buyback_premium_est: Optional[float] = None,
    require_balances: bool = True,
) -> AffordabilityResult:
    """Gate LIVE closes. BUY_TO_CLOSE needs cash; SELL_TO_CLOSE usually does not."""
    instr = (instruction or "").upper()
    have = remaining_tradable(account_cash)

    if instr in ("SELL_TO_CLOSE", "SELL"):
        # Long exit — receiving credit; still require that we can talk to the broker
        if have is None and require_balances:
            return AffordabilityResult(
                False, "account_cash_unavailable", kind="sell_to_close"
            )
        return AffordabilityResult(
            True, "", have=have or 0.0, kind="sell_to_close"
        )

    if instr in ("BUY_TO_CLOSE", "BUY"):
        kind = "buy_to_close"
        if have is None:
            if require_balances:
                return AffordabilityResult(
                    False, "account_cash_unavailable", kind=kind
                )
            return AffordabilityResult(True, "", kind=kind)
        qty = max(1, int(getattr(lot, "quantity", 0) or 1))
        if buyback_premium_est is not None and buyback_premium_est > 0:
            need = float(buyback_premium_est)
        else:
            # Fall back to fill/entry premium * qty * 100 * 1.15 buffer
            prem = _f(getattr(lot, "fill_entry", 0), 0.0)
            if prem <= 0 or prem >= 50:
                meta = getattr(lot, "broker_meta", None) or {}
                prem = _f(meta.get("option_entry_premium"), 0.0)
            if prem <= 0 or prem >= 50:
                prem = _f(getattr(lot, "entry", 0), 0.0)
            if 0 < prem < 50:
                need = round(prem * 100.0 * qty * 1.15, 2)
            else:
                risk = _f(getattr(lot, "max_risk_dollars", 0), 0.0)
                need = round(max(risk, 100.0) * 1.15, 2)
        if have < need:
            return AffordabilityResult(
                False,
                f"insufficient_cash_to_close:need={need:.2f}:have={have:.2f}",
                need=need,
                have=have,
                kind=kind,
            )
        return AffordabilityResult(True, "", need=need, have=have, kind=kind)

    return AffordabilityResult(True, "", kind="unknown")
