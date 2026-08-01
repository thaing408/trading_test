"""Global auto-trade kill switch (halt new entries; optional flatten signal)."""

from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from trading_agent.oms.audit import append_audit, default_oms_dir


def kill_switch_path() -> Path:
    raw = os.getenv("TRADING_AGENT_KILL_SWITCH_FILE", "").strip()
    if raw:
        return Path(raw)
    return default_oms_dir() / "kill_switch.json"


def _env_killed() -> bool:
    return os.getenv("TRADING_AGENT_KILL_SWITCH", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def is_killed() -> bool:
    """True if env flag or on-disk kill switch is active."""
    if _env_killed():
        return True
    path = kill_switch_path()
    try:
        if not path.is_file():
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
        return bool(data.get("active"))
    except (OSError, json.JSONDecodeError, TypeError):
        return False


def kill_switch_status() -> Dict[str, Any]:
    path = kill_switch_path()
    status: Dict[str, Any] = {
        "active": is_killed(),
        "env": _env_killed(),
        "path": str(path),
        "file": None,
    }
    try:
        if path.is_file():
            status["file"] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        status["file"] = {"error": "unreadable"}
    return status


def set_kill_switch(
    reason: str,
    *,
    flatten: bool = False,
    source: str = "manual",
) -> Path:
    path = kill_switch_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "active": True,
        "flatten": bool(flatten),
        "reason": (reason or "unspecified")[:500],
        "source": source,
        "host": socket.gethostname(),
        "set_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    append_audit("kill_switch_set", payload=payload)
    return path


def clear_kill_switch(*, source: str = "manual") -> Path:
    path = kill_switch_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "active": False,
        "flatten": False,
        "reason": "",
        "source": source,
        "host": socket.gethostname(),
        "cleared_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    append_audit("kill_switch_cleared", payload=payload)
    return path


def should_flatten() -> bool:
    """True when kill switch requests flatten-all."""
    if not is_killed():
        return False
    st = kill_switch_status().get("file") or {}
    if isinstance(st, dict) and st.get("flatten"):
        return True
    return os.getenv("TRADING_AGENT_KILL_FLATTEN", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
