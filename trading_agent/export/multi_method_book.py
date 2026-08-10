"""Export multi-method PLAY results into auto_trade_book for OMS/Mac consume.

Paper router → ENTER rows (underlying geometry). Does not place orders.
OMS still applies process gate + kill switch + live flags.
"""

from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from trading_agent.export.auto_trade_book import default_sync_dir, write_auto_trade_book
from trading_agent.strategy.multi_method import TickerMultiEval


def _default_risk_dollars(entry: float, stop: float) -> float:
    """Risk $ for 1 share * 100 share lot, or options-style package floor."""
    try:
        risk_pts = abs(float(entry) - float(stop))
    except (TypeError, ValueError):
        risk_pts = 0.0
    if risk_pts <= 0:
        return 100.0
    # 100-share equity lot risk; cap/floor for book integrity
    raw = risk_pts * 100.0
    return float(max(25.0, min(raw, 2500.0)))


def entry_from_multi_eval(
    result: TickerMultiEval,
    *,
    expires_at: str,
    trading_date: str,
    default_risk_pct: float = 1.0,
) -> Optional[Dict[str, Any]]:
    """Build one ENTER row from a PLAY multi-eval. None if incomplete."""
    if not result.play or result.decision != "PLAY":
        return None

    best = None
    for v in result.votes:
        if v.method_id == result.best_method and v.play:
            best = v
            break
    if best is None:
        play_votes = [v for v in result.votes if v.play and v.method_id != "process_methods"]
        best = max(play_votes, key=lambda v: v.score) if play_votes else None
    if best is None:
        return None

    entry = float(best.entry or 0)
    stop = float(best.stop or 0)
    target = float(best.target or 0)
    if entry <= 0:
        return None
    # Fill missing stop/target from % fallback so risk package is complete
    if stop <= 0:
        if (result.best_side or best.side or "").upper() in ("PUT", "BEAR", "BEARISH", "SHORT"):
            stop = entry * 1.02
        else:
            stop = entry * 0.98
    if target <= 0:
        if stop < entry:
            target = entry + (entry - stop) * 1.5
        else:
            target = entry - (stop - entry) * 1.5
    if stop == target or stop <= 0 or target <= 0:
        return None

    side_raw = (result.best_side or best.side or "CALL").upper()
    if side_raw in ("CALL", "LONG", "BULL", "BULLISH"):
        direction = "Bullish"
        strategy = f"Multi-method long ({result.best_method})"
    elif side_raw in ("PUT", "SHORT", "BEAR", "BEARISH"):
        direction = "Bearish"
        strategy = f"Multi-method short ({result.best_method})"
    else:
        direction = "Neutral"
        strategy = f"Multi-method ({result.best_method})"

    risk = _default_risk_dollars(entry, stop)
    methods = list(result.play_methods or [result.best_method])
    tags = ["multi_method", result.best_method] + [
        m for m in methods if m != result.best_method
    ]
    # dedupe preserve order
    seen = set()
    method_tags = []
    for t in tags:
        if t and t not in seen:
            seen.add(t)
            method_tags.append(t)

    thesis = (
        f"multi-method PLAY agg={result.aggregate_score:.0f}; "
        f"best={result.best_method} {side_raw}; methods={','.join(methods)}"
    )
    notes = "; ".join(result.reasons[:3])[:240]

    return {
        "symbol": result.symbol,
        "action": "ENTER",
        "side": direction,
        "instrument": "equity",  # underlying geometry; no options chain in router
        "strategy": strategy,
        "setup_id": f"multi_{result.best_method}",
        "setup_name": f"Multi-method: {result.best_method}",
        "setup_grade": "B" if result.aggregate_score >= 55 else "C",
        "grade_score": float(result.aggregate_score),
        "entry": round(entry, 4),
        "stop": round(stop, 4),
        "target": round(target, 4),
        "strike_prices": [],
        "expiration": "",
        "max_risk_dollars": round(risk, 2),
        "max_reward_dollars": round(abs(target - entry) * 100.0, 2),
        "max_risk_pct": default_risk_pct,
        "confidence": min(95.0, 50.0 + result.aggregate_score * 0.4),
        "probability_of_success": 0.48,
        "technical_score": float(best.score),
        "fundamental_score": 0.0,
        "quality_score": float(result.aggregate_score),
        "checklist_passed": True,
        "edge_complete": True,
        "auto_trade_eligible": True,
        "defined_risk": True,
        "mtf_note": "",
        "thesis": thesis[:400],
        "expires_at": expires_at,
        "notes": notes,
        "method_tags": method_tags,
        "method_notes": f"source=multi_method_router; play_methods={methods}"[:240],
        "stop_basis": "structure",
        "target_basis": "measured_move",
        "geometry_source": f"multi_method:{result.best_method}",
        "structure_notes": thesis[:240],
        "source": "multi_method_router",
        "trading_date": trading_date,
        "priority_boost": 5.0 + len(methods) * 2.0,
        "quantity": 1,
    }


def build_multi_method_book(
    results: Sequence[TickerMultiEval],
    *,
    merge_entries: Optional[List[Dict[str, Any]]] = None,
    stay_in_cash: bool | None = None,
    regime: str = "multi-method router",
    source_host: str | None = None,
) -> Dict[str, Any]:
    """Build auto_trade_book schema from multi-method results (+ optional merge)."""
    now = datetime.now(timezone.utc)
    expires = now.replace(hour=23, minute=59, second=0, microsecond=0).isoformat()
    trading_date = now.astimezone().date().isoformat()
    host = source_host or socket.gethostname()

    entries: List[Dict[str, Any]] = []
    rejected: List[str] = []
    for r in results:
        if r.decision == "CONFLICT":
            rejected.append(f"{r.symbol}:side_conflict")
            continue
        if r.decision == "NO_DATA":
            rejected.append(f"{r.symbol}:no_data")
            continue
        if not r.play:
            rejected.append(f"{r.symbol}:skip")
            continue
        row = entry_from_multi_eval(r, expires_at=expires, trading_date=trading_date)
        if row is None:
            rejected.append(f"{r.symbol}:incomplete_risk_package")
            continue
        entries.append(row)

    # Merge existing book entries (desk/CIO) — multi-method adds or replaces same symbol
    if merge_entries:
        by_sym = {str(e.get("symbol") or "").upper(): e for e in entries}
        for e in merge_entries:
            if not isinstance(e, dict):
                continue
            sym = str(e.get("symbol") or "").upper()
            if not sym:
                continue
            if sym in by_sym:
                # Prefer multi-method row but keep desk tags
                desk_tags = list(e.get("method_tags") or [])
                mm = by_sym[sym]
                mm_tags = list(mm.get("method_tags") or [])
                for t in desk_tags:
                    if t not in mm_tags:
                        mm_tags.append(t)
                mm["method_tags"] = mm_tags
                mm["merged_with_desk"] = True
            else:
                # keep desk entry as-is
                entries.append(dict(e))

    play_syms = [e["symbol"] for e in entries if e.get("source") == "multi_method_router"]
    watch = play_syms + [
        str(e.get("symbol"))
        for e in entries
        if e.get("source") != "multi_method_router" and e.get("symbol")
    ]
    # dedupe watch
    seen_w = set()
    watchlist = []
    for s in watch:
        u = str(s).upper()
        if u not in seen_w:
            seen_w.add(u)
            watchlist.append(u)

    if stay_in_cash is None:
        # cash only if no entries at all
        stay = len(entries) == 0
    else:
        stay = bool(stay_in_cash) and len(entries) == 0

    return {
        "schema_version": 1,
        "generated_at": now.isoformat(),
        "source_host": host,
        "role": "multi-method-router",
        "trading_date": trading_date,
        "regime": regime,
        "environment_score": 60.0 if entries else 40.0,
        "stay_in_cash": stay,
        "cash_reason": (
            ""
            if entries
            else "Multi-method: no PLAY names with complete risk package"
        ),
        "entries": entries,
        "exits": [],
        "watchlist": watchlist,
        "scan_symbols": watchlist,
        "entry_count": len(entries),
        "rejected_incomplete": rejected[:60],
        "multi_method": {
            "play_count": len(play_syms),
            "scanned": len(results),
            "export": True,
        },
        "broker_boundary": (
            "multi-method-suggest-export; "
            "OMS process gate + live flags still apply"
        ),
    }


def load_existing_auto_trade_book(sync_dir: Path | None = None) -> Dict[str, Any]:
    sync = sync_dir or default_sync_dir()
    candidates = [
        sync / "auto_trade_book.json",
        Path.home() / ".trading_agent" / "sessions" / datetime.now().date().isoformat() / "auto_trade_book.json",
    ]
    for p in candidates:
        try:
            if p.is_file():
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data["_path"] = str(p)
                    return data
        except (OSError, json.JSONDecodeError):
            continue
    return {}


def export_multi_method_auto_trade(
    results: Sequence[TickerMultiEval],
    *,
    merge_desk: bool = True,
    session_dir: Path | None = None,
    sync_dir: Path | None = None,
    stay_in_cash: bool | None = None,
) -> tuple[Dict[str, Any], List[Path]]:
    """Build + write auto_trade_book from multi-method PLAY set.

    merge_desk: keep existing desk/CIO entries and add multi-method PLAYs.
    """
    merge_entries = None
    regime = "multi-method router"
    if merge_desk:
        existing = load_existing_auto_trade_book(sync_dir)
        if existing:
            merge_entries = list(existing.get("entries") or [])
            if existing.get("regime"):
                regime = f"{existing.get('regime')} + multi-method"

    # Respect process cash bias if set
    if stay_in_cash is None:
        try:
            from trading_agent.runbook.process import load_day_state

            st = load_day_state()
            if (st.bias or "").lower() == "cash":
                stay_in_cash = True
        except Exception:
            pass

    book = build_multi_method_book(
        results,
        merge_entries=merge_entries,
        stay_in_cash=stay_in_cash,
        regime=regime,
    )
    # If human set cash bias, force empty multi-method entries only — keep desk? fail closed empty all
    if stay_in_cash is True:
        book["entries"] = []
        book["entry_count"] = 0
        book["stay_in_cash"] = True
        book["cash_reason"] = "process bias=cash — multi-method export suppressed"
        book["watchlist"] = []

    paths = write_auto_trade_book(book, session_dir=session_dir, sync_dir=sync_dir)
    return book, paths
