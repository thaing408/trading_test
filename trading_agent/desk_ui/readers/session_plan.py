"""Load daily_plan_context and merge rejection rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from trading_agent.desk_ui.json_io import read_json_file
from trading_agent.desk_ui.models import RejectionRow
from trading_agent.desk_ui.paths import session_dir_for
from trading_agent.session.context import load_saved_plan_context


@dataclass
class PlanLoadResult:
    data: dict[str, Any]
    path: str | None
    error: str | None


def load_plan_context(
    trading_date: date,
    *,
    state: Path | None = None,
) -> PlanLoadResult:
    if state is not None:
        path = Path(state) / "sessions" / trading_date.isoformat() / "daily_plan_context.json"
    else:
        path = session_dir_for(trading_date) / "daily_plan_context.json"

    if not path.is_file():
        return PlanLoadResult(data={}, path=str(path), error="missing")

    # Prefer shared loader when file is complete; fall back to safe read.
    try:
        data = load_saved_plan_context(path)
        if isinstance(data, dict):
            return PlanLoadResult(data=data, path=str(path), error=None)
    except Exception:
        pass

    data, err = read_json_file(path)
    if err or not isinstance(data, dict):
        return PlanLoadResult(data={}, path=str(path), error=err or "not_object")
    return PlanLoadResult(data=data, path=str(path), error=None)


def heuristic_gate_tags(reason: str) -> list[str]:
    """Display-only gate tags from free-text rejection reasons."""
    r = reason or ""
    rl = r.lower()
    tags: list[str] = []
    checks = [
        ("adr", ("adr%", "adr ", "adr%")),
        ("rvol", ("relative volume", "rvol", "rel vol")),
        ("strength_52w", ("52w", "52-week", "strength")),
        ("checklist", ("checklist",)),
        ("edge", ("edge", "incomplete edge")),
        ("risk_package", ("incomplete_risk", "risk package", "risk_package")),
        ("grade", ("grade", "setup grade")),
        ("mtf", ("mtf", "multi-timeframe", "timeframe")),
    ]
    for tag, needles in checks:
        for n in needles:
            if n in rl:
                if tag not in tags:
                    tags.append(tag)
                break
    # Case-sensitive ADR% sometimes written exactly
    if "ADR%" in r and "adr" not in tags:
        tags.insert(0, "adr")
    return tags


def merge_rejections(
    plan: dict[str, Any],
    book: dict[str, Any],
) -> list[RejectionRow]:
    """Merge plan rejection_reasons + book rejected_incomplete with dedupe."""
    rows: list[RejectionRow] = []
    seen: set[tuple[str, str, str]] = set()

    for item in plan.get("rejection_reasons") or []:
        if isinstance(item, dict):
            symbol = str(item.get("symbol") or "").strip().upper()
            reason = str(item.get("reason") or "").strip()
        else:
            continue
        if not symbol and not reason:
            continue
        key = ("plan", symbol, reason)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            RejectionRow(
                symbol=symbol or "?",
                reason=reason,
                source="plan",
                gates=heuristic_gate_tags(reason),
            )
        )

    for item in book.get("rejected_incomplete") or []:
        if isinstance(item, dict):
            symbol = str(item.get("symbol") or "").strip().upper()
            reason = str(item.get("reason") or item.get("kind") or "").strip()
        else:
            s = str(item or "").strip()
            symbol, _, kind = s.partition(":")
            symbol = symbol.strip().upper()
            reason = (kind or s).strip()
        if not symbol and not reason:
            continue
        key = ("book_incomplete", symbol, reason)
        if key in seen:
            continue
        seen.add(key)
        gates = heuristic_gate_tags(reason)
        if reason and reason not in gates and ":" not in str(item):
            # kind-only tags
            kind_tag = reason.lower().replace(" ", "_")[:40]
            if kind_tag and kind_tag not in gates:
                gates = gates + [kind_tag]
        rows.append(
            RejectionRow(
                symbol=symbol or "?",
                reason=reason or str(item),
                source="book_incomplete",
                gates=gates,
            )
        )

    source_rank = {"plan": 0, "book_incomplete": 1}

    def _sort_key(r: RejectionRow) -> tuple:
        return (r.symbol.upper(), source_rank.get(r.source, 9), r.reason)

    rows.sort(key=_sort_key)
    return rows
