"""Immutable-ish JSONL audit trail for auto-trade decisions."""

from __future__ import annotations

import json
import os
import socket
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def default_oms_dir() -> Path:
    raw = os.getenv("TRADING_AGENT_OMS_DIR", "").strip()
    if raw:
        return Path(raw)
    return Path.home() / ".trading_agent" / "oms"


def audit_path(day: Optional[date] = None) -> Path:
    d = day or datetime.now(timezone.utc).date()
    return default_oms_dir() / "audit" / f"audit_{d.isoformat()}.jsonl"


def append_audit(
    event: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    day: Optional[date] = None,
) -> Path:
    """Append one audit event. Never raises for disk errors (returns path attempted)."""
    path = audit_path(day)
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


def read_audit(day: Optional[date] = None, *, limit: int = 500) -> list[dict]:
    path = audit_path(day)
    if not path.is_file():
        return []
    rows: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return rows[-limit:]
