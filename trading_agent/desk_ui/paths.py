"""State roots for desk UI — reuse existing defaults."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from trading_agent.export.auto_trade_book import default_sync_dir
from trading_agent.oms.audit import default_oms_dir
from trading_agent.session.context import default_session_dir


def state_root() -> Path:
    """``~/.trading_agent`` (or TRADING_AGENT_STATE_ROOT)."""
    raw = os.getenv("TRADING_AGENT_STATE_ROOT", "").strip()
    if raw:
        return Path(raw)
    return Path.home() / ".trading_agent"


def sync_dir() -> Path:
    return default_sync_dir()


def oms_dir() -> Path:
    return default_oms_dir()


def session_dir_for(trading_date: date, base: Path | None = None) -> Path:
    """Session folder; does not require the path to exist for reads."""
    if base is not None:
        return Path(base) / trading_date.isoformat()
    root = state_root() / "sessions"
    return root / trading_date.isoformat()


def ensure_session_dir(trading_date: date) -> Path:
    """Create session dir via existing helper (may mkdir)."""
    return default_session_dir(trading_date, base=state_root() / "sessions")


def ui_sidecar_dir() -> Path:
    return state_root() / "ui"


def process_cards_path(trading_date: date) -> Path:
    return state_root() / "process" / f"{trading_date.isoformat()}.json"


def desk_session_lock_path() -> Path:
    return state_root() / "logs" / "desk_session.lock"
