"""JSONL log for adaptive manage cadence + exit recommendations (live desk).

Purpose: measure whether 3m-in-position vs 15m-flat checking correlates with
early exits / over-management. One line per event; fail-closed on disk errors.
"""

from __future__ import annotations

import json
import os
import socket
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def default_manage_log_dir() -> Path:
    raw = os.getenv("TRADING_AGENT_MANAGE_LOG_DIR", "").strip()
    if raw:
        return Path(raw)
    return Path.home() / ".trading_agent" / "logs" / "manage"


def manage_log_path(day: Optional[date] = None) -> Path:
    d = day or datetime.now(timezone.utc).date()
    return default_manage_log_dir() / f"manage_{d.isoformat()}.jsonl"


def manage_logging_enabled() -> bool:
    return os.getenv("TRADING_AGENT_MANAGE_LOG", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def append_manage_event(
    event: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    day: Optional[date] = None,
) -> Path:
    path = manage_log_path(day)
    if not manage_logging_enabled():
        return path
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "host": socket.gethostname(),
        "event": event,
        "payload": payload or {},
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
    except OSError:
        pass
    return path


def log_interval_decision(
    *,
    cycle: int,
    wait_minutes: int,
    baseline_minutes: int,
    in_position_minutes: int,
    has_open_positions: bool,
    open_symbols: Optional[Sequence[str]] = None,
) -> Path:
    return append_manage_event(
        "interval_decision",
        payload={
            "cycle": cycle,
            "wait_minutes": wait_minutes,
            "baseline_minutes": baseline_minutes,
            "in_position_minutes": in_position_minutes,
            "has_open_positions": has_open_positions,
            "open_symbols": list(open_symbols or []),
            "mode": "in_position_fast" if has_open_positions else "flat_baseline",
        },
    )


def log_manage_recommendations(
    *,
    cycle: int,
    wait_minutes: int,
    has_open_positions: bool,
    recommendations: Sequence[Any],
) -> Path:
    recs: List[Dict[str, Any]] = []
    for rec in recommendations:
        recs.append(
            {
                "symbol": getattr(rec, "symbol", ""),
                "action": getattr(rec, "action", ""),
                "why": (getattr(rec, "why_recommended", "") or "")[:240],
                "what_changed": (getattr(rec, "what_changed", "") or "")[:240],
                "prob": getattr(rec, "updated_probability", None),
                "conf": getattr(rec, "updated_confidence", None),
                "alerts": [
                    {
                        "type": getattr(a, "alert_type", ""),
                        "severity": getattr(a, "severity", ""),
                        "message": (getattr(a, "message", "") or "")[:160],
                    }
                    for a in (getattr(rec, "alerts", None) or [])
                ],
            }
        )
    exitish = [
        r
        for r in recs
        if str(r.get("action") or "").lower()
        in ("exit", "scale out", "hedge", "trim", "close")
    ]
    return append_manage_event(
        "manage_cycle",
        payload={
            "cycle": cycle,
            "wait_minutes": wait_minutes,
            "has_open_positions": has_open_positions,
            "n_recommendations": len(recs),
            "n_exitish": len(exitish),
            "recommendations": recs,
            "exitish": exitish,
        },
    )


def summarize_manage_log(path: Optional[Path] = None, day: Optional[date] = None) -> Dict[str, Any]:
    """Aggregate one day of manage logs for review."""
    p = path or manage_log_path(day)
    if not p.is_file():
        return {"path": str(p), "events": 0, "intervals": {}, "exit_actions": {}}
    intervals: Dict[str, int] = {}
    exit_actions: Dict[str, int] = {}
    n = 0
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            n += 1
            ev = row.get("event")
            pl = row.get("payload") or {}
            if ev == "interval_decision":
                mode = str(pl.get("mode") or "unknown")
                intervals[mode] = intervals.get(mode, 0) + 1
            if ev == "manage_cycle":
                for r in pl.get("recommendations") or []:
                    act = str(r.get("action") or "unknown")
                    exit_actions[act] = exit_actions.get(act, 0) + 1
    except OSError:
        pass
    return {
        "path": str(p),
        "events": n,
        "intervals": intervals,
        "exit_actions": exit_actions,
    }
