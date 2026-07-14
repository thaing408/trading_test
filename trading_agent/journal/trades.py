"""Closed-trade journal schema for Performance + dual-system learning."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class JournalTrade:
    symbol: str
    entry: float
    exit: float
    profit_loss: float
    strategy: str
    setup_id: str = ""
    setup_name: str = ""
    setup_grade: str = ""
    checklist_passed: bool | None = None
    direction: str = ""
    stop_loss: float = 0.0
    profit_target: float = 0.0
    confidence_score: float = 0.0
    fundamental_score: float = 0.0
    quality_score: float = 0.0
    exit_reason: str = ""
    holding_time_minutes: int = 0
    source_host: str = ""
    entry_time: str = ""
    exit_time: str = ""
    discovery_slot: str = ""
    revenge_reentry: bool = False
    notes: str = ""


def default_journal_dir() -> Path:
    sync = os.getenv("TRADING_AGENT_SYNC_DIR", "").strip()
    root = Path(sync) if sync else Path.home() / ".trading_agent" / "sync"
    return root / "journal"


def journal_path_for(day: date | None = None) -> Path:
    env = os.getenv("TRADING_AGENT_TRADES_FILE", "").strip()
    if env:
        return Path(env)
    d = day or date.today()
    return default_journal_dir() / f"trades_{d.isoformat()}.json"


def append_journal_trade(trade: JournalTrade, path: Path | None = None) -> Path:
    p = path or journal_path_for()
    p.parent.mkdir(parents=True, exist_ok=True)
    rows: List[dict] = []
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            rows = list(data.get("trades") or [])
        except (json.JSONDecodeError, OSError):
            rows = []
    rows.append(asdict(trade))
    p.write_text(json.dumps({"trades": rows, "updated_at": datetime.now(timezone.utc).isoformat()}, indent=2) + "\n", encoding="utf-8")
    return p


def load_journal_trades(path: Path | None = None) -> List[dict]:
    p = path or journal_path_for()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return list(data.get("trades") or [])
    except (json.JSONDecodeError, OSError):
        return []
