"""Watch researcher gap_screener_book.json and prep auto-trade for new continuation names.

trading_agent does not poll a background thread by default; the desk/intraday loop
calls ``check_and_process_gap_book`` each cycle. On file create/update (mtime/hash)
or newly appeared continuation symbols, we re-run research on an expanded symbol
set and export auto_trade_book.json so Mac / ENTER path can pick them up.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from trading_agent.config import AgentConfig
from trading_agent.export.gap_book import (
    continuation_symbols,
    default_sync_dir,
    gap_book_paths,
    load_gap_book,
)


def watch_state_path() -> Path:
    return default_sync_dir() / "gap_book_watch_state.json"


@dataclass
class GapWatchSnapshot:
    """Result of one watch check."""

    file_path: str = ""
    file_exists: bool = False
    changed: bool = False
    mtime: float = 0.0
    content_hash: str = ""
    continuation: List[str] = field(default_factory=list)
    new_continuation: List[str] = field(default_factory=list)
    dropped_continuation: List[str] = field(default_factory=list)
    all_candidates: List[str] = field(default_factory=list)
    as_of: str = ""
    message: str = ""


@dataclass
class GapAutoTradePrepResult:
    """Outcome of preparing auto-trade after a gap book change."""

    triggered: bool
    snapshot: GapWatchSnapshot
    symbols_researched: List[str] = field(default_factory=list)
    opportunities: int = 0
    enter_symbols: List[str] = field(default_factory=list)
    stay_in_cash: bool = True
    export_paths: List[str] = field(default_factory=list)
    discord_message: str = ""
    error: str = ""


def _file_fingerprint(path: Path) -> tuple[float, str]:
    if not path.is_file():
        return 0.0, ""
    mtime = path.stat().st_mtime
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()[:16]
    return mtime, digest


def load_watch_state(path: Path | None = None) -> Dict[str, Any]:
    p = path or watch_state_path()
    try:
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return {
        "mtime": 0.0,
        "content_hash": "",
        "continuation": [],
        "processed_continuation": [],
        "last_check": "",
        "last_file": "",
    }


def save_watch_state(state: Dict[str, Any], path: Path | None = None) -> Path:
    p = path or watch_state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    state = dict(state)
    state["last_check"] = datetime.now(timezone.utc).isoformat()
    p.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return p


def resolve_gap_book_file() -> Optional[Path]:
    for p in gap_book_paths():
        if p.is_file():
            return p
    return None


def inspect_gap_book_changes(state: Dict[str, Any] | None = None) -> GapWatchSnapshot:
    """Compare on-disk gap book to last watch state (no side effects beyond read)."""
    prev = state if state is not None else load_watch_state()
    path = resolve_gap_book_file()
    snap = GapWatchSnapshot()
    if path is None:
        snap.message = "gap_screener_book.json not found"
        return snap

    snap.file_path = str(path)
    snap.file_exists = True
    mtime, digest = _file_fingerprint(path)
    snap.mtime = mtime
    snap.content_hash = digest

    book = load_gap_book(path)
    snap.as_of = str(book.get("as_of") or "")
    cont = sorted(continuation_symbols(book))
    snap.continuation = cont
    snap.all_candidates = sorted(
        {
            str(r.get("symbol") or "").upper()
            for r in (book.get("candidates") or [])
            if r.get("symbol")
        }
    )

    prev_hash = str(prev.get("content_hash") or "")
    prev_mtime = float(prev.get("mtime") or 0)
    prev_cont = {str(s).upper() for s in (prev.get("continuation") or [])}
    processed = {str(s).upper() for s in (prev.get("processed_continuation") or [])}

    snap.changed = (digest != prev_hash) or (mtime > prev_mtime + 1e-6) or not prev_hash
    current = set(cont)
    # New for auto-trade prep = in continuation now and never processed (or re-seen after fill drop)
    snap.new_continuation = sorted(current - processed)
    # Also treat brand-new vs last continuation snapshot
    brand_new = sorted(current - prev_cont)
    if brand_new and not snap.new_continuation:
        snap.new_continuation = brand_new
    # Prefer union of not-yet-processed
    snap.new_continuation = sorted(set(snap.new_continuation) | (current - processed))
    snap.dropped_continuation = sorted(prev_cont - current)

    if snap.changed:
        snap.message = (
            f"Gap book updated ({path.name}) hash={digest} "
            f"continuation={len(cont)} new={snap.new_continuation}"
        )
    else:
        snap.message = f"Gap book unchanged hash={digest} continuation={len(cont)}"
    return snap


def format_gap_watch_discord(result: GapAutoTradePrepResult) -> str:
    snap = result.snapshot
    lines = [
        "**Gap book watch → auto-trade prep**",
        f"File: `{Path(snap.file_path).name if snap.file_path else 'missing'}`",
        f"Changed: **{snap.changed}** | Continuation: **{len(snap.continuation)}**",
    ]
    if snap.new_continuation:
        lines.append(f"**New continuation tickers:** {', '.join(snap.new_continuation)}")
    if snap.dropped_continuation:
        lines.append(
            f"No longer continuation: {', '.join(snap.dropped_continuation[:12])}"
        )
    if result.error:
        lines.append(f"**Error:** {result.error}")
        return "\n".join(lines)
    if not result.triggered:
        lines.append("_No new continuation names to research._")
        return "\n".join(lines)

    lines.append(f"Researched **{len(result.symbols_researched)}** symbols")
    lines.append(
        f"Tradeable setups: **{result.opportunities}** | "
        f"ENTER ready: **{', '.join(result.enter_symbols) or 'none'}**"
    )
    if result.stay_in_cash and not result.enter_symbols:
        lines.append("_Stay in cash — new gap names did not pass desk gates (yet)._")
    elif result.enter_symbols:
        lines.append(
            "_Auto-trade book refreshed — Mac / ENTER path can pick up tagged rows "
            "(`gap_continuation_4d`)._"
        )
    if result.export_paths:
        lines.append(f"Export: `{result.export_paths[0]}`")
    return "\n".join(lines)


def _merge_symbol_universe(base: List[str], extra: List[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for s in list(extra) + list(base):
        u = str(s or "").upper().strip()
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def prepare_auto_trade_for_symbols(
    symbols: List[str],
    agent_config: AgentConfig,
    *,
    session_dir: Path | None = None,
) -> GapAutoTradePrepResult:
    """Run research pipeline focused on symbols and export auto_trade_book."""
    from copy import deepcopy

    from trading_agent.export.auto_trade_book import export_plan_for_execution
    from trading_agent.pipeline import run_pipeline

    snap = GapWatchSnapshot(new_continuation=list(symbols), continuation=list(symbols))
    if not symbols:
        return GapAutoTradePrepResult(triggered=False, snapshot=snap)

    base_syms = list(agent_config.screener.symbols or [])
    merged = _merge_symbol_universe(base_syms, symbols)
    max_n = int(os.getenv("TRADING_AGENT_GAP_WATCH_MAX_SYMBOLS", "40") or 40)
    if len(merged) > max_n:
        keep = _merge_symbol_universe([], symbols)
        for s in base_syms:
            if len(keep) >= max_n:
                break
            if s.upper() not in {x.upper() for x in keep}:
                keep.append(s.upper())
        merged = keep[:max_n]

    cfg = deepcopy(agent_config)
    cfg.screener.symbols = merged

    try:
        plan = run_pipeline(cfg)
        paths: List[str] = []
        book: Dict[str, Any] = {}
        try:
            book = export_plan_for_execution(plan, session_dir=session_dir)
            paths = list(book.get("_written_paths") or [])
        except Exception as exp_exc:  # noqa: BLE001
            return GapAutoTradePrepResult(
                triggered=True,
                snapshot=snap,
                symbols_researched=merged,
                opportunities=len(plan.ranked_opportunities),
                error=f"export failed: {exp_exc}",
            )
        enters = [
            str(e.get("symbol") or "").upper()
            for e in (book.get("entries") or [])
            if e.get("symbol")
        ]
        gap_enters = [
            e
            for e in (book.get("entries") or [])
            if e.get("gap_continuation")
            or "gap_continuation_4d" in (e.get("method_tags") or [])
        ]
        enter_syms = [str(e.get("symbol")).upper() for e in gap_enters] or enters
        result = GapAutoTradePrepResult(
            triggered=True,
            snapshot=snap,
            symbols_researched=merged,
            opportunities=len(plan.ranked_opportunities),
            enter_symbols=enter_syms,
            stay_in_cash=bool(book.get("stay_in_cash", plan.stay_in_cash)),
            export_paths=paths,
        )
        result.discord_message = format_gap_watch_discord(result)
        return result
    except Exception as exc:  # noqa: BLE001
        return GapAutoTradePrepResult(
            triggered=True,
            snapshot=snap,
            symbols_researched=merged,
            error=str(exc),
            discord_message=f"**Gap auto-trade prep failed:** {exc}",
        )


def check_and_process_gap_book(
    agent_config: AgentConfig,
    *,
    session_dir: Path | None = None,
    force: bool = False,
    process_all_continuation_if_changed: bool = True,
) -> GapAutoTradePrepResult:
    """Watch gap book file; on change/new tickers, research and export auto-trade book.

    Parameters
    ----------
    force:
        Process even if file hash unchanged (still only researches unprocessed names
        unless none pending then all continuation).
    process_all_continuation_if_changed:
        When file changes, research all current continuation symbols (not only delta).
    """
    state = load_watch_state()
    snap = inspect_gap_book_changes(state)

    if not snap.file_exists:
        return GapAutoTradePrepResult(
            triggered=False,
            snapshot=snap,
            discord_message=snap.message,
        )

    should_run = force or snap.changed or bool(snap.new_continuation)
    if not should_run:
        # Still refresh last_check
        state["last_check"] = datetime.now(timezone.utc).isoformat()
        save_watch_state(state)
        return GapAutoTradePrepResult(
            triggered=False,
            snapshot=snap,
            discord_message=snap.message,
        )

    # Symbols to research
    if process_all_continuation_if_changed and snap.changed and snap.continuation:
        targets = list(snap.continuation)
    else:
        targets = list(snap.new_continuation) or list(snap.continuation)

    if not targets:
        # File changed but no continuation names — update state only
        state.update(
            {
                "mtime": snap.mtime,
                "content_hash": snap.content_hash,
                "continuation": snap.continuation,
                "last_file": snap.file_path,
            }
        )
        save_watch_state(state)
        snap.message = "Gap book changed but no continuation symbols"
        return GapAutoTradePrepResult(
            triggered=False,
            snapshot=snap,
            discord_message=snap.message,
        )

    result = prepare_auto_trade_for_symbols(
        targets,
        agent_config,
        session_dir=session_dir,
    )
    result.snapshot = snap
    result.snapshot.new_continuation = [
        s for s in targets if s in set(snap.new_continuation) or s in set(snap.continuation)
    ]
    if not result.discord_message:
        result.discord_message = format_gap_watch_discord(result)

    # Mark processed (even if stay in cash — we tried)
    processed = {str(s).upper() for s in (state.get("processed_continuation") or [])}
    processed |= {s.upper() for s in targets}
    # Drop symbols no longer in continuation so they can re-trigger later
    processed &= set(snap.continuation) | {s.upper() for s in targets}
    state.update(
        {
            "mtime": snap.mtime,
            "content_hash": snap.content_hash,
            "continuation": snap.continuation,
            "processed_continuation": sorted(processed),
            "last_file": snap.file_path,
            "last_prep": {
                "symbols": targets,
                "enters": result.enter_symbols,
                "opportunities": result.opportunities,
                "error": result.error,
                "at": datetime.now(timezone.utc).isoformat(),
            },
        }
    )
    save_watch_state(state)
    return result
