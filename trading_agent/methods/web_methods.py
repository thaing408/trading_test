"""Public best-practice trading methods (process frameworks, not paid tips).

Fetches optional public pages and merges with a curated baseline of edge rules
used industry-wide: predefined risk, checklist trading, multi-timeframe bias,
position sizing caps, and no revenge re-entry. Fail-open to baseline if network fails.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class MethodTag:
    method_id: str
    name: str
    rule: str
    source: str
    weight: float = 1.0  # influence on eligibility notes


# Curated process methods (public domain process ideas — not copyrighted book text)
BASELINE_METHODS: tuple[MethodTag, ...] = (
    MethodTag(
        "predefined_risk",
        "Predefined risk package",
        "Every trade must define direction, entry, stop, target, and max risk before entry",
        "baseline:risk_management",
        1.2,
    ),
    MethodTag(
        "checklist_edge",
        "Checklist / playbook edge",
        "Only trade named setups that pass a written checklist; skip incomplete setups",
        "baseline:playbook_process",
        1.2,
    ),
    MethodTag(
        "htf_bias",
        "Higher-timeframe bias",
        "Do not take lower-timeframe signals against a clear higher-timeframe trend bias",
        "baseline:multi_timeframe",
        1.1,
    ),
    MethodTag(
        "size_cap",
        "Unit risk cap",
        "Risk a small fixed fraction of capital per trade; never increase size from emotion",
        "baseline:position_sizing",
        1.1,
    ),
    MethodTag(
        "no_revenge",
        "No revenge re-entry",
        "After a stop-out, wait a cool-down before re-entering the same symbol",
        "baseline:discipline",
        1.0,
    ),
    MethodTag(
        "expectancy_focus",
        "Expectancy over win rate",
        "Prefer positive expectancy (R-multiple) setups over high win-rate low-edge noise",
        "baseline:expectancy",
        1.0,
    ),
    MethodTag(
        "volume_participation",
        "Volume / participation",
        "Breakouts and momentum need above-average volume; fade low-participation spikes",
        "baseline:volume",
        1.0,
    ),
    MethodTag(
        "lfd_structure_stop",
        "Last Full Day / structure stop",
        "After breakout, place initial risk at Last Full Day (Brandt) and classify path Type 1–4; prefer structure stops over fixed %",
        "baseline:brand_lfd_techcharts",
        1.15,
    ),
    MethodTag(
        "event_risk",
        "Event risk filter",
        "Reduce or skip new risk into binary events (earnings) without an explicit plan",
        "baseline:events",
        1.0,
    ),
)

# Public educational pages (process-oriented). Used only to reinforce tag keywords.
DEFAULT_METHOD_URLS: tuple[str, ...] = (
    "https://www.investopedia.com/articles/trading/09/risk-management.asp",
    "https://www.investopedia.com/articles/trading/08/position-sizing.asp",
    "https://www.investopedia.com/terms/e/expectancy.asp",
)

_KEYWORD_TO_METHOD: Dict[str, str] = {
    "stop-loss": "predefined_risk",
    "stop loss": "predefined_risk",
    "risk management": "predefined_risk",
    "position siz": "size_cap",
    "risk per trade": "size_cap",
    "expectancy": "expectancy_focus",
    "risk-reward": "expectancy_focus",
    "risk reward": "expectancy_focus",
    "volume": "volume_participation",
    "trend": "htf_bias",
    "time frame": "htf_bias",
    "timeframe": "htf_bias",
    "discipline": "no_revenge",
    "emotional": "no_revenge",
}


def _fetch_url_text(url: str, *, timeout: float = 8.0) -> str:
    req = Request(
        url,
        headers={"User-Agent": "trading_agent-method-research/1.0 (educational)"},
    )
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — explicit allowlist URLs
        raw = resp.read(400_000)
    text = raw.decode("utf-8", errors="ignore")
    # Strip tags roughly
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def reinforce_methods_from_text(text: str, methods: Sequence[MethodTag]) -> List[MethodTag]:
    """Bump weight when public page text mentions method keywords."""
    by_id = {m.method_id: m for m in methods}
    bumped: Dict[str, float] = {}
    for kw, mid in _KEYWORD_TO_METHOD.items():
        if kw in text and mid in by_id:
            bumped[mid] = bumped.get(mid, 0.0) + 0.15
    out: List[MethodTag] = []
    for m in methods:
        w = m.weight + bumped.get(m.method_id, 0.0)
        out.append(
            MethodTag(
                method_id=m.method_id,
                name=m.name,
                rule=m.rule,
                source=m.source + ("+web" if m.method_id in bumped else ""),
                weight=round(min(2.0, w), 2),
            )
        )
    return out


def research_trading_methods(
    *,
    use_network: bool = True,
    urls: Sequence[str] | None = None,
) -> List[MethodTag]:
    """Return structured method tags. Offline/fixture → baseline only."""
    methods = list(BASELINE_METHODS)
    if not use_network:
        return methods
    combined = ""
    for url in urls or DEFAULT_METHOD_URLS:
        try:
            combined += " " + _fetch_url_text(url)
        except Exception:
            continue
    if not combined.strip():
        return methods
    return reinforce_methods_from_text(combined, methods)


def methods_as_dict(methods: Sequence[MethodTag]) -> List[Dict[str, Any]]:
    return [
        {
            "method_id": m.method_id,
            "name": m.name,
            "rule": m.rule,
            "source": m.source,
            "weight": m.weight,
        }
        for m in methods
    ]


def evaluate_methods_for_setup(
    methods: Sequence[MethodTag],
    context: Mapping[str, Any],
) -> Dict[str, Any]:
    """Score how well a candidate satisfies researched method rules.

    Returns tags applied, pass/fail per method_id, and reject reasons.
    Fail closed for auto-trade only when critical methods fail (risk package, checklist).
    """
    applied: List[str] = []
    failures: List[str] = []
    critical_fail = False

    entry = float(context.get("entry_price") or context.get("entry") or 0)
    stop = float(context.get("stop_loss") or context.get("stop") or 0)
    target = float(context.get("profit_target") or context.get("target") or 0)
    checklist = context.get("checklist_passed")
    edge = context.get("edge_complete")
    align = str(context.get("timeframe_alignment") or "").lower()
    rvol = float(context.get("relative_volume") or 0)
    direction = str(context.get("direction") or "").lower()
    earnings_days = context.get("days_to_earnings")
    revenge = bool(context.get("revenge_reentry") or False)
    risk_pct = float(context.get("proposed_risk_pct") or context.get("max_risk_pct") or 0)
    max_risk = float(context.get("max_risk_per_trade_pct") or 2.0)

    for m in methods:
        mid = m.method_id
        ok = True
        reason = ""
        if mid == "predefined_risk":
            ok = entry > 0 and stop > 0 and target > 0 and stop != target
            if not ok:
                reason = "missing entry/stop/target"
                critical_fail = True
        elif mid == "checklist_edge":
            ok = checklist is not False  # None treated soft-pass if not required yet
            if context.get("require_checklist") and not checklist:
                ok = False
                reason = "checklist not passed"
                critical_fail = True
        elif mid == "htf_bias":
            if align == "conflicting":
                ok = False
                reason = "multi-TF conflicting"
                critical_fail = True
        elif mid == "size_cap":
            if risk_pct > 0 and risk_pct > max_risk + 1e-9:
                ok = False
                reason = f"risk {risk_pct}% > cap {max_risk}%"
                critical_fail = True
        elif mid == "no_revenge":
            if revenge:
                ok = False
                reason = "revenge re-entry"
                critical_fail = True
        elif mid == "volume_participation":
            setup = str(context.get("setup_id") or "")
            if "breakout" in setup or "breakdown" in setup:
                if rvol > 0 and rvol < 1.3:
                    ok = False
                    reason = f"low RVOL {rvol:.2f}x on breakout"
        elif mid == "event_risk":
            try:
                dte = int(earnings_days) if earnings_days is not None else None
            except (TypeError, ValueError):
                dte = None
            if dte is not None and 0 <= dte <= 2:
                ok = False
                reason = f"earnings in {dte}d"
                # soft for watchlist; critical for auto if configured
                if context.get("strict_events"):
                    critical_fail = True
        elif mid == "expectancy_focus":
            if entry > 0 and stop > 0 and target > 0:
                risk_pts = abs(entry - stop)
                reward_pts = abs(target - entry)
                if risk_pts > 0 and reward_pts / risk_pts < 1.0:
                    ok = False
                    reason = "R:R below 1.0"
        elif mid == "lfd_structure_stop":
            # Prefer structure-backed stops (LFD / negation / S-R); soft-fail pure ATR %
            basis = str(context.get("stop_basis") or "").lower()
            lfd_lvl = float(context.get("lfd_level") or 0)
            brk_lvl = float(context.get("breakout_level") or 0)
            if entry > 0 and stop > 0:
                if basis in ("lfd", "negation", "support", "resistance"):
                    ok = True
                elif lfd_lvl > 0 or brk_lvl > 0:
                    ok = True
                elif basis in ("atr", "") and not lfd_lvl and not brk_lvl:
                    ok = False
                    reason = "stop not structure-backed (no LFD/breakout levels)"
                    # Soft by default — critical only when auto path requires structure
                    if context.get("require_structure_stop"):
                        critical_fail = True
            else:
                ok = False
                reason = "missing entry/stop for structure package"
        if ok:
            applied.append(mid)
        else:
            failures.append(f"{mid}: {reason or 'failed'}")

    return {
        "method_ids_ok": applied,
        "method_failures": failures,
        "critical_fail": critical_fail,
        "method_notes": [f"{m.method_id}:{m.rule}" for m in methods[:6]],
    }


def format_methods_for_discord(methods: Sequence[MethodTag], limit: int = 6) -> List[str]:
    lines = []
    for m in methods[:limit]:
        lines.append(f"- **{m.name}** (`{m.method_id}`): {m.rule}")
    return lines
