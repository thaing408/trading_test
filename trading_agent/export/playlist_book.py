"""Load researcher watchlist playlist for soft desk / discovery merge.

Watch-list remains human-first and is NOT auto-trade approval.
Candidates are merged into the screener universe and tagged so CIO can see them;
all normal gates still apply.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from trading_agent.export.gap_book import default_sync_dir


def playlist_book_paths() -> List[Path]:
    sync = default_sync_dir()
    return [
        sync / "watchlist_playlist.json",
        Path.home() / ".trading_agent" / "watchlist" / "playlist.json",
    ]


def load_playlist_book(path: Path | None = None) -> Dict[str, Any]:
    candidates = [path] if path is not None else playlist_book_paths()
    for p in candidates:
        if p is None:
            continue
        try:
            if p.is_file():
                return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return {}


def playlist_candidate_symbols(book: Dict[str, Any] | None = None) -> List[str]:
    """Ordered symbols that cleared researcher playlist gates (may be empty)."""
    data = book if book is not None else load_playlist_book()
    out: List[str] = []
    seen: Set[str] = set()
    for row in data.get("candidates") or []:
        if isinstance(row, str):
            sym = row.upper().strip()
        elif isinstance(row, dict):
            sym = str(row.get("symbol") or "").upper().strip()
        else:
            continue
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out


def merge_playlist_into_symbols(
    symbols: List[str] | None,
    *,
    book: Dict[str, Any] | None = None,
    enabled: bool | None = None,
) -> List[str]:
    """Prepend playlist names into a symbol list (deduped)."""
    if enabled is None:
        raw = os.getenv("TRADING_AGENT_PLAYLIST_MERGE", "1").strip().lower()
        enabled = raw not in ("0", "false", "no", "off")
    if not enabled:
        return list(symbols or [])
    base = [str(s).upper().strip() for s in (symbols or []) if s]
    extra = playlist_candidate_symbols(book)
    if not extra:
        return base
    seen = set(base)
    merged = list(base)
    for s in extra:
        if s not in seen:
            seen.add(s)
            merged.append(s)
    return merged


def apply_playlist_tag(
    symbol: str,
    method_tags: List[str] | None,
    *,
    book: Dict[str, Any] | None = None,
) -> tuple[List[str], str]:
    """Soft tag if symbol is on the researcher's playlist (not approval)."""
    tags = list(method_tags or [])
    note = ""
    data = book if book is not None else load_playlist_book()
    candidates = playlist_candidate_symbols(data)
    sym = symbol.upper().strip()
    if sym not in candidates:
        return tags, note
    if "watchlist_playlist" not in tags:
        tags.append("watchlist_playlist")
    note = (
        f"Researcher playlist candidate (score see watchlist_playlist.json); "
        f"not CIO-approved by playlist alone"
    )
    return tags, note
