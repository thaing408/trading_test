"""Options-specific process methods and eligibility gates.

Public best practices (not paid signals):
- Match strategy to IV rank (sell premium when IV high; buy debit when IV low)
- Prefer defined-risk structures when possible
- Liquidity: OI + bid-ask spread floors
- POP / R:R awareness for credit vs debit
- Avoid binary risk into earnings without explicit plan
- DTE window: avoid ultra-short unless 0DTE playbook
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence

from trading_agent.methods.web_methods import MethodTag


OPTIONS_BASELINE_METHODS: tuple[MethodTag, ...] = (
    MethodTag(
        "iv_regime_match",
        "IV regime ↔ strategy",
        "High IVR: favor credit/defined-risk premium; low IVR: debit spreads or long options",
        "options:iv_rank",
        1.3,
    ),
    MethodTag(
        "defined_risk",
        "Defined risk preference",
        "Prefer spreads/condors with known max loss; naked short only if explicitly allowed",
        "options:defined_risk",
        1.2,
    ),
    MethodTag(
        "options_liquidity",
        "Options liquidity",
        "Require adequate open interest and tight bid-ask before auto ENTER",
        "options:liquidity",
        1.2,
    ),
    MethodTag(
        "pop_rr_credit",
        "Credit spread POP / width",
        "Credit strategies need sensible POP and defined wing width vs underlying",
        "options:credit",
        1.1,
    ),
    MethodTag(
        "debit_rr",
        "Debit R:R",
        "Debit long premium needs target > risk (avoid lottery tickets as core book)",
        "options:debit",
        1.1,
    ),
    MethodTag(
        "dte_window",
        "DTE window",
        "Standard book uses weekly–monthly DTE; sub-3 DTE only for named 0DTE playbooks",
        "options:dte",
        1.0,
    ),
    MethodTag(
        "greeks_sanity",
        "Delta / direction consistency",
        "Bullish structures should not be short-delta heavy; bearish not long-delta heavy",
        "options:greeks",
        1.0,
    ),
    MethodTag(
        "earnings_options",
        "Earnings binary risk",
        "Skip new short premium into earnings; long premium only with explicit event plan",
        "options:events",
        1.1,
    ),
)

CREDIT_STRATEGIES = frozenset(
    {
        "Iron Condor",
        "Bull Put Credit Spread",
        "Bear Call Credit Spread",
        "Covered Call",
        "Cash Secured Put",
    }
)
DEBIT_STRATEGIES = frozenset(
    {
        "Long Call",
        "Long Put",
        "Debit Spread",
        "Calendar Spread",
        "Diagonal Spread",
    }
)
DEFINED_RISK = frozenset(
    {
        "Iron Condor",
        "Bull Put Credit Spread",
        "Bear Call Credit Spread",
        "Debit Spread",
        "Calendar Spread",
        "Diagonal Spread",
        "Long Call",
        "Long Put",
    }
)
# Covered call / CSP are defined in equity terms but larger notional
SEMI_DEFINED = frozenset({"Covered Call", "Cash Secured Put"})


@dataclass
class OptionsMethodResult:
    ok: bool
    critical_fail: bool
    method_ids_ok: List[str]
    failures: List[str]
    strategy_class: str  # credit | debit | other
    notes: List[str]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "critical_fail": self.critical_fail,
            "method_ids_ok": self.method_ids_ok,
            "failures": self.failures,
            "strategy_class": self.strategy_class,
            "notes": self.notes,
        }


def classify_strategy(name: str) -> str:
    if name in CREDIT_STRATEGIES:
        return "credit"
    if name in DEBIT_STRATEGIES:
        return "debit"
    return "other"


def is_defined_risk_strategy(name: str) -> bool:
    return name in DEFINED_RISK or name in SEMI_DEFINED


def evaluate_options_methods(
    context: Mapping[str, Any],
    *,
    methods: Sequence[MethodTag] | None = None,
    min_iv_high: float = 55.0,
    max_iv_low: float = 40.0,
    min_oi: int = 500,
    max_spread_pct: float = 5.0,
    min_pop_credit: float = 0.45,
    min_rr_debit: float = 1.0,
    min_dte: int = 3,
    max_dte: int = 60,
    allow_odte: bool = False,
    strict_earnings: bool = True,
) -> OptionsMethodResult:
    """Gate options suggestions using IV regime, liquidity, POP/RR, DTE, events."""
    methods = list(methods or OPTIONS_BASELINE_METHODS)
    name = str(context.get("strategy") or context.get("strategy_name") or "")
    ivr = float(context.get("iv_rank") or 0)
    pop = float(context.get("probability_of_profit") or context.get("pop") or 0)
    oi = int(context.get("open_interest") or 0)
    spread = float(context.get("bid_ask_spread_pct") or 0)
    dte = int(context.get("expiration_days") or context.get("dte") or 30)
    delta = float(context.get("delta") or 0.5)
    direction = str(context.get("direction") or "").lower()
    entry = float(context.get("entry_price") or 0)
    stop = float(context.get("stop_loss") or 0)
    target = float(context.get("profit_target") or 0)
    max_risk = float(context.get("maximum_risk") or 0)
    max_reward = float(context.get("maximum_reward") or 0)
    setup_id = str(context.get("setup_id") or "")
    days_to_earnings = context.get("days_to_earnings")

    sc = classify_strategy(name)
    applied: List[str] = []
    failures: List[str] = []
    notes: List[str] = [f"strategy_class={sc}"]
    critical = False

    for m in methods:
        mid = m.method_id
        ok = True
        reason = ""

        if mid == "iv_regime_match":
            if sc == "credit" and ivr > 0 and ivr < max_iv_low:
                ok = False
                reason = f"credit strategy but IVR {ivr:.0f} low (<{max_iv_low:.0f})"
                critical = True
            elif sc == "debit" and ivr >= min_iv_high:
                # Soft: debit in high IV is expensive — flag critical for auto
                ok = False
                reason = f"debit strategy but IVR {ivr:.0f} high (≥{min_iv_high:.0f})"
                critical = True
            elif sc == "credit":
                notes.append(f"IVR {ivr:.0f} supports premium selling")
            elif sc == "debit":
                notes.append(f"IVR {ivr:.0f} supports debit/long premium")

        elif mid == "defined_risk":
            if name and not is_defined_risk_strategy(name):
                ok = False
                reason = f"{name} not treated as defined-risk for auto ENTER"
                critical = True
            elif name in SEMI_DEFINED:
                notes.append(f"{name}: equity-defined risk — size carefully")

        elif mid == "options_liquidity":
            if oi > 0 and oi < min_oi:
                ok = False
                reason = f"OI {oi} < {min_oi}"
                critical = True
            if spread > max_spread_pct:
                ok = False
                reason = (reason + "; " if reason else "") + f"spread {spread:.1f}% > {max_spread_pct}%"
                critical = True

        elif mid == "pop_rr_credit":
            if sc == "credit":
                if pop > 0 and pop < min_pop_credit:
                    ok = False
                    reason = f"credit POP {pop:.0%} < {min_pop_credit:.0%}"
                    critical = True
                if max_risk > 0 and max_reward > 0 and max_reward > max_risk * 1.5:
                    # unusual for credit — soft note
                    notes.append("credit max_reward unusually large vs risk — verify model")

        elif mid == "debit_rr":
            if sc == "debit":
                rr = 0.0
                if max_risk > 0 and max_reward > 0:
                    rr = max_reward / max_risk
                elif entry > 0 and stop > 0 and target > 0:
                    risk_pts = abs(entry - stop)
                    if risk_pts > 0:
                        rr = abs(target - entry) / risk_pts
                if rr > 0 and rr < min_rr_debit:
                    ok = False
                    reason = f"debit R:R {rr:.2f} < {min_rr_debit}"
                    critical = True

        elif mid == "dte_window":
            is_odte_play = "odte" in setup_id.lower() or "0dte" in setup_id.lower()
            if dte < min_dte and not (allow_odte or is_odte_play):
                ok = False
                reason = f"DTE {dte} < {min_dte} without 0DTE playbook"
                critical = True
            if dte > max_dte:
                ok = False
                reason = f"DTE {dte} > {max_dte}"
                # soft for LEAPs — not critical
                notes.append(reason)

        elif mid == "greeks_sanity":
            if direction in ("bullish", "long") and delta < -0.15:
                ok = False
                reason = f"bullish setup with delta {delta:.2f}"
                critical = True
            if direction in ("bearish", "short") and delta > 0.15:
                # long put has negative delta — OK
                if "Put" not in name and "put" not in name.lower():
                    if sc == "credit" and "Call" in name:
                        pass  # short call credit can be ok
                    elif delta > 0.35 and sc == "debit" and "Call" in name:
                        pass
                    else:
                        notes.append(f"delta {delta:.2f} vs {direction} — verify structure")

        elif mid == "earnings_options":
            try:
                dte_earn = int(days_to_earnings) if days_to_earnings is not None else None
            except (TypeError, ValueError):
                dte_earn = None
            if dte_earn is not None and 0 <= dte_earn <= 2:
                if sc == "credit":
                    ok = False
                    reason = f"short premium into earnings ({dte_earn}d)"
                    if strict_earnings:
                        critical = True
                else:
                    notes.append(f"earnings in {dte_earn}d — long premium event risk")

        if ok:
            applied.append(mid)
        else:
            failures.append(f"{mid}: {reason or 'failed'}")

    return OptionsMethodResult(
        ok=len(failures) == 0 or not critical,
        critical_fail=critical,
        method_ids_ok=applied,
        failures=failures,
        strategy_class=sc,
        notes=notes,
    )


def options_methods_as_dict() -> List[Dict[str, Any]]:
    return [
        {
            "method_id": m.method_id,
            "name": m.name,
            "rule": m.rule,
            "source": m.source,
            "weight": m.weight,
        }
        for m in OPTIONS_BASELINE_METHODS
    ]
