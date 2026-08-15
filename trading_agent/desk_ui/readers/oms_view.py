"""Read-only OMS lots + kill switch."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_oms_lots(*, oms_root: Path | None = None) -> list[dict[str, Any]]:
    try:
        from trading_agent.oms.state import OmsStore

        store = OmsStore(root=oms_root)
        return [lot.to_dict() for lot in store.open_lots()]
    except Exception:
        return []


def load_kill_switch() -> dict[str, Any]:
    try:
        from trading_agent.oms.kill_switch import kill_switch_status

        return kill_switch_status()
    except Exception:
        return {"active": False, "path": None, "file": None, "env": False}
