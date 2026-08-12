"""Shared scanned-list artifact for trading_test + trading_agent.

Both products read/write the **same paths** under the sync dir so methods lab
and the live CIO desk look at one universe / watchlist.

Canonical files (schema_version 2):
  ``~/.trading_agent/sync/scanned_list.json``
  ``~/.trading_agent/sync/auto_trade_scan_symbols.json``  (compat mirror)

Also mirrored to ``~/.grok/state/`` when writable.

Env:
  TRADING_AGENT_SYNC_DIR — override sync root
  TRADING_AGENT_SCANNED_LIST — explicit path to scanned_list.json
"""

from __future__ import annotations

import json
import os
import socket
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

SCHEMA_VERSION = 2
CANONICAL_NAME = "scanned_list.json"
COMPAT_NAME = "auto_trade_scan_symbols.json"


def default_sync_dir() -> Path:
    raw = os.getenv("TRADING_AGENT_SYNC_DIR", "").strip()
    if raw:
        return Path(raw)
    return Path.home() / ".trading_agent" / "sync"


def scanned_list_path(sync_dir: Path | None = None) -> Path:
    explicit = os.getenv("TRADING_AGENT_SCANNED_LIST", "").strip()
    if explicit:
        return Path(explicit)
    return (sync_dir or default_sync_dir()) / CANONICAL_NAME


def _normalize_symbols(raw: Sequence[Any] | None) -> List[str]:
    out: List[str] = []
    for item in raw or []:
        if isinstance(item, dict):
            sym = str(item.get("symbol") or item.get("ticker") or "").upper().strip()
        else:
            sym = str(item).upper().strip()
        if not sym or sym in out:
            continue
        # Drop fixture junk if it ever reappears
        if sym in ("PENNY", "NONE", "NULL", "CASH"):
            continue
        out.append(sym)
    return out


def empty_scanned_list(
    *,
    source_product: str = "",
    source_phase: str = "",
    trading_date: str | None = None,
) -> Dict[str, Any]:
    td = trading_date or date.today().isoformat()
    return {
        "schema_version": SCHEMA_VERSION,
        "trading_date": td,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source_product": source_product or os.getenv("TRADING_AGENT_PRODUCT", ""),
        "source_phase": source_phase,
        "source_host": socket.gethostname(),
        "universe": [],
        "watchlist": [],
        "play_symbols": [],
        "scan_symbols": [],
        "symbols": [],
        "stay_in_cash": True,
        "notes": [],
        "symbol_meta": {},
    }


def build_scanned_list(
    *,
    universe: Sequence[str] | None = None,
    watchlist: Sequence[str] | None = None,
    play_symbols: Sequence[str] | None = None,
    stay_in_cash: bool | None = None,
    source_product: str = "",
    source_phase: str = "",
    trading_date: str | None = None,
    notes: Sequence[str] | None = None,
    symbol_meta: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a normalized scanned-list document."""
    uni = _normalize_symbols(universe)
    watch = _normalize_symbols(watchlist)
    plays = _normalize_symbols(play_symbols)
    # Ensure plays ⊆ universe; watch filled from plays then rest of universe
    for s in plays:
        if s not in uni:
            uni.append(s)
    if not watch:
        watch = list(plays) if plays else list(uni[:20])
    for s in watch:
        if s not in uni:
            uni.append(s)
    scan = list(dict.fromkeys(watch + uni))
    if stay_in_cash is None:
        stay_in_cash = len(plays) == 0
    try:
        from trading_agent.product import PRODUCT_ID

        product = source_product or PRODUCT_ID
    except Exception:
        product = source_product or os.getenv("TRADING_AGENT_PRODUCT", "unknown")

    return {
        "schema_version": SCHEMA_VERSION,
        "trading_date": trading_date or date.today().isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source_product": product,
        "source_phase": source_phase,
        "source_host": socket.gethostname(),
        "universe": uni,
        "watchlist": watch,
        "play_symbols": plays,
        "scan_symbols": scan,
        "symbols": scan,  # alias for older readers
        "stay_in_cash": bool(stay_in_cash),
        "notes": list(notes or []),
        "symbol_meta": dict(symbol_meta or {}),
    }


def write_scanned_list(
    doc: Dict[str, Any],
    *,
    session_dir: Path | None = None,
    sync_dir: Path | None = None,
) -> List[Path]:
    """Persist canonical + compat + optional session copies."""
    sync = Path(sync_dir) if sync_dir is not None else default_sync_dir()
    grok_state = Path.home() / ".grok" / "state"
    payload = json.dumps(doc, indent=2) + "\n"
    # Compat payload (v1-ish fields for pulse/auto-trade)
    compat = {
        "schema_version": 1,
        "trading_date": doc.get("trading_date"),
        "updated_at": doc.get("updated_at"),
        "symbols": list(doc.get("scan_symbols") or doc.get("symbols") or []),
        "scan_symbols": list(doc.get("scan_symbols") or doc.get("symbols") or []),
        "watchlist": list(doc.get("watchlist") or []),
        "play_symbols": list(doc.get("play_symbols") or []),
        "universe": list(doc.get("universe") or []),
        "stay_in_cash": doc.get("stay_in_cash"),
        "source": doc.get("source_product") or "scanned_list",
        "source_phase": doc.get("source_phase"),
        "source_host": doc.get("source_host"),
    }
    compat_payload = json.dumps(compat, indent=2) + "\n"

    targets_canon = [
        scanned_list_path(sync),
        grok_state / CANONICAL_NAME,
    ]
    targets_compat = [
        sync / COMPAT_NAME,
        grok_state / COMPAT_NAME,
    ]
    if session_dir is not None:
        sd = Path(session_dir)
        targets_canon.append(sd / CANONICAL_NAME)
        targets_compat.append(sd / COMPAT_NAME)
        # date archive
        td = str(doc.get("trading_date") or "unknown")
        targets_canon.append(sync / "archive" / f"scanned_list_{td}.json")

    paths: List[Path] = []
    for path in targets_canon:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload, encoding="utf-8")
            paths.append(path)
        except OSError:
            continue
    for path in targets_compat:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(compat_payload, encoding="utf-8")
            paths.append(path)
        except OSError:
            continue
    return paths


def load_scanned_list(
    *,
    sync_dir: Path | None = None,
    max_age_hours: float | None = 36.0,
    require_today: bool = False,
) -> Optional[Dict[str, Any]]:
    """Load newest readable scanned list (canonical preferred, then compat)."""
    sync = Path(sync_dir) if sync_dir is not None else default_sync_dir()
    candidates = [
        scanned_list_path(sync),
        Path.home() / ".grok" / "state" / CANONICAL_NAME,
        sync / COMPAT_NAME,
        Path.home() / ".grok" / "state" / COMPAT_NAME,
        Path.home() / ".trading_agent" / "sync" / CANONICAL_NAME,
        Path.home() / ".trading_agent" / "sync" / COMPAT_NAME,
    ]
    explicit = os.getenv("TRADING_AGENT_SCANNED_LIST", "").strip()
    if explicit:
        candidates.insert(0, Path(explicit))

    today = date.today().isoformat()
    best: Optional[Dict[str, Any]] = None
    best_mtime = -1.0
    for path in candidates:
        try:
            if not path.is_file():
                continue
            mtime = path.stat().st_mtime
            if max_age_hours is not None:
                age_h = (datetime.now().timestamp() - mtime) / 3600.0
                if age_h > max_age_hours:
                    continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            if require_today and str(data.get("trading_date") or "") != today:
                continue
            # Normalize aliases
            data = _coerce_doc(data)
            if mtime >= best_mtime:
                best = data
                best_mtime = mtime
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
    return best


def _coerce_doc(data: Dict[str, Any]) -> Dict[str, Any]:
    uni = _normalize_symbols(
        data.get("universe") or data.get("scan_symbols") or data.get("symbols")
    )
    watch = _normalize_symbols(data.get("watchlist") or data.get("symbols"))
    plays = _normalize_symbols(data.get("play_symbols") or [])
    if not uni:
        uni = list(dict.fromkeys(watch + plays))
    if not watch:
        watch = list(plays) if plays else list(uni[:20])
    scan = _normalize_symbols(data.get("scan_symbols") or data.get("symbols") or uni)
    out = dict(data)
    out["schema_version"] = int(data.get("schema_version") or SCHEMA_VERSION)
    out["universe"] = uni
    out["watchlist"] = watch
    out["play_symbols"] = plays
    out["scan_symbols"] = scan or uni
    out["symbols"] = out["scan_symbols"]
    return out


def symbols_from_scanned_list(
    *,
    prefer: str = "universe",
    limit: int = 0,
    sync_dir: Path | None = None,
    max_age_hours: float | None = 36.0,
) -> List[str]:
    """Return symbols for scanners. prefer: universe | watchlist | play_symbols."""
    doc = load_scanned_list(sync_dir=sync_dir, max_age_hours=max_age_hours)
    if not doc:
        return []
    key = prefer if prefer in ("universe", "watchlist", "play_symbols", "scan_symbols") else "universe"
    syms = list(doc.get(key) or doc.get("scan_symbols") or doc.get("universe") or [])
    if limit > 0:
        return syms[:limit]
    return syms


def publish_scanned_list(
    *,
    universe: Sequence[str] | None = None,
    watchlist: Sequence[str] | None = None,
    play_symbols: Sequence[str] | None = None,
    stay_in_cash: bool | None = None,
    source_product: str = "",
    source_phase: str = "",
    trading_date: str | None = None,
    notes: Sequence[str] | None = None,
    session_dir: Path | None = None,
    sync_dir: Path | None = None,
    symbol_meta: Dict[str, Any] | None = None,
) -> tuple[Dict[str, Any], List[Path]]:
    """Build + write shared scanned list. Returns (doc, paths)."""
    doc = build_scanned_list(
        universe=universe,
        watchlist=watchlist,
        play_symbols=play_symbols,
        stay_in_cash=stay_in_cash,
        source_product=source_product,
        source_phase=source_phase,
        trading_date=trading_date,
        notes=notes,
        symbol_meta=symbol_meta,
    )
    paths = write_scanned_list(doc, session_dir=session_dir, sync_dir=sync_dir)
    return doc, paths


def merge_publish_from_book(
    book: Dict[str, Any],
    *,
    source_phase: str = "auto_trade_book",
    session_dir: Path | None = None,
    sync_dir: Path | None = None,
) -> tuple[Dict[str, Any], List[Path]]:
    """Publish shared list from an auto_trade_book dict (desk or multi-method)."""
    mm = book.get("multi_method") or {}
    plays: List[str] = []
    for e in book.get("entries") or []:
        if isinstance(e, dict) and e.get("symbol"):
            plays.append(str(e["symbol"]))
    # Prefer explicit multi-method play list if present
    if mm.get("play_symbols"):
        plays = list(mm["play_symbols"]) + plays
    return publish_scanned_list(
        universe=book.get("scan_symbols") or book.get("watchlist") or plays,
        watchlist=book.get("watchlist") or plays,
        play_symbols=plays,
        stay_in_cash=book.get("stay_in_cash"),
        source_product=str(book.get("role") or book.get("source_host") or ""),
        source_phase=source_phase,
        trading_date=str(book.get("trading_date") or "") or None,
        notes=[str(book.get("cash_reason") or "")[:200]] if book.get("cash_reason") else None,
        session_dir=session_dir,
        sync_dir=sync_dir,
    )
