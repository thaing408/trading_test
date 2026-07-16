"""Load researcher gap screener book for auto-trade / ranking boosts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


def default_sync_dir() -> Path:
    raw = os.getenv("TRADING_AGENT_SYNC_DIR", "").strip()
    if raw:
        return Path(raw)
    return Path.home() / ".trading_agent" / "sync"


def gap_book_paths() -> List[Path]:
    sync = default_sync_dir()
    return [
        sync / "gap_screener_book.json",
        Path.home() / ".researcher" / "gap_screener_book.json",
    ]


def load_gap_book(path: Path | None = None) -> Dict[str, Any]:
    """Load latest gap screener book (empty dict if missing)."""
    candidates = [path] if path is not None else gap_book_paths()
    for p in candidates:
        if p is None:
            continue
        try:
            if p.is_file():
                return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return {}


def continuation_symbols(book: Dict[str, Any] | None = None) -> Set[str]:
    """Symbols tagged continuation (unfilled ≥4 sessions)."""
    data = book if book is not None else load_gap_book()
    out: Set[str] = set()
    for row in data.get("continuation") or []:
        sym = str(row.get("symbol") or "").upper().strip()
        if sym:
            out.add(sym)
    # Fallback: scan candidates
    if not out:
        for row in data.get("candidates") or []:
            if str(row.get("state") or "") == "continuation":
                sym = str(row.get("symbol") or "").upper().strip()
                if sym:
                    out.add(sym)
    return out


def gap_meta_for_symbol(symbol: str, book: Dict[str, Any] | None = None) -> Optional[Dict[str, Any]]:
    data = book if book is not None else load_gap_book()
    sym = symbol.upper().strip()
    for row in data.get("candidates") or []:
        if str(row.get("symbol") or "").upper() == sym:
            return dict(row)
    return None


def apply_gap_boost_to_opportunity_fields(
    *,
    symbol: str,
    method_tags: List[str],
    auto_trade_eligible: bool,
    book: Dict[str, Any] | None = None,
) -> tuple[List[str], bool, str]:
    """Return (method_tags, auto_trade_eligible, note) with gap continuation boost.

    Continuation symbols get method tag `gap_continuation_4d` and remain/boost eligible
    only when already checklist/edge ready (caller still enforces gates).
    """
    tags = list(method_tags or [])
    note = ""
    meta = gap_meta_for_symbol(symbol, book)
    if not meta:
        return tags, auto_trade_eligible, note
    state = str(meta.get("state") or "")
    bias = str(meta.get("continuation_bias") or "none")
    if state == "continuation":
        if "gap_continuation_4d" not in tags:
            tags.append("gap_continuation_4d")
        note = (
            f"Gap screener: {meta.get('direction')} {meta.get('gap_pct')}% on "
            f"{meta.get('gap_date')} day {int(meta.get('days_since_gap') or 0) + 1} "
            f"unfilled — bias {bias}"
        )
        # Soft boost: do not force ENTER if other gates fail; tag only.
        # Optional hard prefer: TRADING_AGENT_GAP_BOOST_AUTO=1 keeps eligible as-is.
    elif state == "full_fill":
        if "gap_filled" not in tags:
            tags.append("gap_filled")
        note = "Gap screener: full fill — no continuation boost"
    elif state == "open_watch":
        if "gap_open_watch" not in tags:
            tags.append("gap_open_watch")
        note = (
            f"Gap screener: open watch day {int(meta.get('days_since_gap') or 0) + 1}/4"
        )
    return tags, auto_trade_eligible, note
