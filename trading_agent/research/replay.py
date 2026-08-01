"""Replay CIO / risk decisions on stored session candidates (G3.8)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def default_session_dir(day: str) -> Path:
    return Path.home() / ".trading_agent" / "sessions" / day


def load_session_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _candidate_rows(session: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Best-effort extract of candidates / opportunities from session artifacts."""
    rows: List[Dict[str, Any]] = []
    for key in (
        "opportunities",
        "candidates",
        "cio_candidates",
        "research_opportunities",
        "entries",
    ):
        block = session.get(key)
        if isinstance(block, list):
            rows.extend(r for r in block if isinstance(r, dict))
    # nested plan
    plan = session.get("daily_plan") or session.get("plan") or {}
    if isinstance(plan, dict):
        for key in ("opportunities", "top_opportunities", "candidates"):
            block = plan.get(key)
            if isinstance(block, list):
                rows.extend(r for r in block if isinstance(r, dict))
    return rows


def replay_session_candidates(
    session_dir: Path | str,
    *,
    apply_risk: bool = True,
) -> Dict[str, Any]:
    """Reconstruct a lightweight decision summary from a session folder.

    Does not re-fetch market data. Uses stored numbers and re-applies
    eligibility heuristics for audit / post-mortem.
    """
    root = Path(session_dir)
    artifacts = {}
    for name in (
        "daily_plan_context.json",
        "cio_inputs.json",
        "cio_report.json",
        "auto_trade_book.json",
        "research.json",
        "session.json",
    ):
        data = load_session_json(root / name)
        if data:
            artifacts[name] = data

    all_rows: List[Dict[str, Any]] = []
    for data in artifacts.values():
        all_rows.extend(_candidate_rows(data))

    # de-dupe by symbol+setup
    seen = set()
    uniq: List[Dict[str, Any]] = []
    for row in all_rows:
        key = (
            str(row.get("symbol") or "").upper(),
            str(row.get("setup_id") or row.get("strategy") or ""),
            str(row.get("entry") or row.get("entry_price") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        uniq.append(row)

    decisions: List[Dict[str, Any]] = []
    for row in uniq:
        symbol = str(row.get("symbol") or "").upper()
        entry = float(row.get("entry") or row.get("entry_price") or 0)
        stop = float(row.get("stop") or row.get("stop_loss") or 0)
        target = float(row.get("target") or row.get("profit_target") or 0)
        risk = float(row.get("max_risk_dollars") or 0)
        eligible = row.get("auto_trade_eligible")
        reasons: List[str] = []
        action = "review"
        if apply_risk:
            if not symbol:
                action, reasons = "reject", ["missing_symbol"]
            elif entry <= 0 or stop <= 0 or target <= 0:
                action, reasons = "reject", ["incomplete_risk_package"]
            elif eligible is False:
                action, reasons = "reject", ["not_auto_eligible"]
            elif risk <= 0:
                action, reasons = "reject", ["missing_risk_budget"]
            else:
                action, reasons = "pass", []
        decisions.append(
            {
                "symbol": symbol,
                "setup_id": row.get("setup_id") or row.get("strategy"),
                "entry": entry,
                "stop": stop,
                "target": target,
                "max_risk_dollars": risk,
                "auto_trade_eligible": eligible,
                "replay_action": action,
                "reasons": reasons,
            }
        )

    book = artifacts.get("auto_trade_book.json") or {}
    book_entries = book.get("entries") if isinstance(book, dict) else None

    return {
        "session_dir": str(root),
        "artifacts": list(artifacts.keys()),
        "candidate_count": len(uniq),
        "pass_count": sum(1 for d in decisions if d["replay_action"] == "pass"),
        "reject_count": sum(1 for d in decisions if d["replay_action"] == "reject"),
        "decisions": decisions,
        "auto_trade_book_entries": len(book_entries or []) if isinstance(book_entries, list) else 0,
        "stay_in_cash": bool(book.get("stay_in_cash")) if isinstance(book, dict) else None,
    }


def format_replay_report(result: Dict[str, Any]) -> str:
    lines = [
        f"# Session replay: {result.get('session_dir')}",
        f"Artifacts: {', '.join(result.get('artifacts') or []) or '(none)'}",
        f"Candidates: {result.get('candidate_count')}  "
        f"pass={result.get('pass_count')} reject={result.get('reject_count')}",
        f"Book entries: {result.get('auto_trade_book_entries')}  "
        f"stay_in_cash={result.get('stay_in_cash')}",
        "",
        "## Decisions",
    ]
    for d in result.get("decisions") or []:
        lines.append(
            f"- [{d.get('replay_action')}] {d.get('symbol')} "
            f"{d.get('setup_id')} entry={d.get('entry')} "
            f"reasons={d.get('reasons')}"
        )
    if not result.get("decisions"):
        lines.append("- (no candidates found in session artifacts)")
    return "\n".join(lines) + "\n"
