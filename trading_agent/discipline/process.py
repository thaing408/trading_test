"""Steenbarger + Bellafiore process review: setup attribution beyond P/L."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Sequence


@dataclass
class ProcessScore:
    setup_id: str
    setup_name: str
    checklist_passed: bool
    plan_adherence: float  # 0-100
    grade_at_entry: str
    process_score: float  # 0-100 composite
    notes: List[str] = field(default_factory=list)


def score_process(
    *,
    setup_id: str = "",
    setup_name: str = "",
    checklist_passed: bool | None = None,
    plan_adherence: float | None = None,
    grade_at_entry: str = "",
    followed_stop: bool | None = None,
    followed_target_rule: bool | None = None,
    revenge_reentry: bool = False,
) -> ProcessScore:
    notes: List[str] = []
    score = 50.0
    name = setup_name or setup_id or "untagged"

    if checklist_passed is True:
        score += 20
        notes.append("Checklist passed at entry")
    elif checklist_passed is False:
        score -= 25
        notes.append("Checklist failed or incomplete at entry")

    adherence = plan_adherence
    if adherence is None:
        # Derive from flags
        flags = []
        if followed_stop is True:
            flags.append(1.0)
        elif followed_stop is False:
            flags.append(0.0)
        if followed_target_rule is True:
            flags.append(1.0)
        elif followed_target_rule is False:
            flags.append(0.5)
        adherence = (sum(flags) / len(flags) * 100) if flags else 50.0

    adherence = max(0.0, min(100.0, float(adherence)))
    score += (adherence - 50) * 0.4
    notes.append(f"Plan adherence {adherence:.0f}/100")

    g = (grade_at_entry or "").upper()
    if g in ("A+", "A"):
        score += 10
        notes.append(f"Grade at entry {g}")
    elif g == "F":
        score -= 15
        notes.append("Entered on F-grade — process breach")
    elif g:
        notes.append(f"Grade at entry {g}")

    if revenge_reentry:
        score -= 20
        notes.append("Revenge re-entry after stop — process violation")

    score = round(max(0.0, min(100.0, score)), 1)
    return ProcessScore(
        setup_id=setup_id or "",
        setup_name=name,
        checklist_passed=bool(checklist_passed),
        plan_adherence=adherence,
        grade_at_entry=g or "n/a",
        process_score=score,
        notes=notes,
    )


def process_from_trade_row(trade: Mapping[str, Any]) -> ProcessScore:
    return score_process(
        setup_id=str(trade.get("setup_id") or trade.get("playbook_setup_id") or ""),
        setup_name=str(trade.get("setup_name") or trade.get("playbook_name") or ""),
        checklist_passed=trade.get("checklist_passed"),
        plan_adherence=trade.get("plan_adherence"),
        grade_at_entry=str(trade.get("grade_at_entry") or trade.get("setup_grade") or ""),
        followed_stop=trade.get("followed_stop"),
        followed_target_rule=trade.get("followed_target_rule"),
        revenge_reentry=bool(trade.get("revenge_reentry", False)),
    )


def setup_attribution_stats(trades: Sequence[Mapping[str, Any] | Any]) -> Dict[str, dict]:
    """Aggregate process + P/L by setup_id for review."""
    buckets: Dict[str, dict] = defaultdict(
        lambda: {
            "n": 0,
            "wins": 0,
            "pnl": 0.0,
            "process_sum": 0.0,
            "checklist_pass": 0,
            "name": "",
        }
    )
    for t in trades:
        if hasattr(t, "__dataclass_fields__"):
            row = {f: getattr(t, f) for f in t.__dataclass_fields__}  # type: ignore[attr-defined]
        elif isinstance(t, Mapping):
            row = dict(t)
        else:
            continue
        sid = str(row.get("setup_id") or row.get("playbook_setup_id") or "untagged")
        b = buckets[sid]
        b["n"] += 1
        b["name"] = str(row.get("setup_name") or row.get("playbook_name") or sid)
        pnl = float(row.get("profit_loss") or 0)
        b["pnl"] += pnl
        if pnl > 0:
            b["wins"] += 1
        ps = process_from_trade_row(row)
        b["process_sum"] += ps.process_score
        if row.get("checklist_passed") is True:
            b["checklist_pass"] += 1
    out = {}
    for sid, b in buckets.items():
        n = max(1, b["n"])
        out[sid] = {
            "setup_id": sid,
            "setup_name": b["name"],
            "trade_count": b["n"],
            "win_rate": b["wins"] / n,
            "total_pnl": round(b["pnl"], 2),
            "avg_process_score": round(b["process_sum"] / n, 1),
            "checklist_pass_rate": round(b["checklist_pass"] / n, 2),
        }
    return out


def process_insights_from_trades(trades: Sequence[Any]) -> List[str]:
    """At least one improvement/habit driven by setup process fields (not P/L alone)."""
    rows = []
    for t in trades:
        if hasattr(t, "__dataclass_fields__"):
            rows.append({f: getattr(t, f) for f in t.__dataclass_fields__})  # type: ignore
        elif isinstance(t, Mapping):
            rows.append(dict(t))
    if not rows:
        return [
            "Process review: no tagged trades — journal setup_id and checklist_passed next session"
        ]

    stats = setup_attribution_stats(rows)
    insights: List[str] = []

    # Prefer process quality over pure P/L
    by_process = sorted(
        stats.values(), key=lambda x: (x["avg_process_score"], x["total_pnl"]), reverse=True
    )
    by_process_weak = sorted(stats.values(), key=lambda x: x["avg_process_score"])

    best = by_process[0]
    insights.append(
        f"Process habit: best adherence on play '{best['setup_name']}' "
        f"(avg process {best['avg_process_score']:.0f}/100, checklist pass "
        f"{best['checklist_pass_rate']:.0%}, n={best['trade_count']}) — replicate checklist"
    )

    weak = by_process_weak[0]
    if weak["setup_id"] != best["setup_id"] or weak["avg_process_score"] < 55:
        insights.append(
            f"Process improvement: play '{weak['setup_name']}' avg process "
            f"{weak['avg_process_score']:.0f}/100 — review failed checklist items before size-up"
        )

    revenge = [r for r in rows if r.get("revenge_reentry")]
    if revenge:
        insights.append(
            f"Discipline: {len(revenge)} revenge re-entry trade(s) tagged — enforce cool-down rail"
        )

    incomplete = [
        r
        for r in rows
        if r.get("checklist_passed") is False
        or not (r.get("setup_id") or r.get("playbook_setup_id"))
    ]
    if incomplete:
        insights.append(
            f"Playbook: {len(incomplete)} trade(s) missing pass checklist/setup tag — "
            "only named plays with full checklist should auto-trade"
        )

    return insights
