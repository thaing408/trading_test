"""Export multi-method PLAY results into auto_trade_book for OMS/Mac consume.

Paper/test: **options debit** rows (single-leg CALL/PUT), not share lots.
Underlying entry/stop/target are structure levels used to pick strike & risk.
OMS still applies process gate + kill switch + live flags.
"""

from __future__ import annotations

import json
import os
import socket
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from zoneinfo import ZoneInfo

from trading_agent.export.auto_trade_book import default_sync_dir, write_auto_trade_book
from trading_agent.strategy.multi_method import (
    MultiMethodConfig,
    TickerMultiEval,
    passes_export_quality,
)

ET = ZoneInfo("America/New_York")


def _default_risk_dollars(entry: float, stop: float) -> float:
    """Risk $ floor for 1 debit option contract package."""
    try:
        risk_pts = abs(float(entry) - float(stop))
    except (TypeError, ValueError):
        risk_pts = 0.0
    if risk_pts <= 0:
        return 150.0
    # Rough: structure risk × 100 as package cap; options size still 1 contract
    raw = risk_pts * 100.0 * 0.15  # not full stock notional
    return float(max(50.0, min(raw, 500.0)))


def _nearest_option_expiration(from_day: date | None = None, *, max_dte: int = 5) -> date:
    """Legacy helper — prefer dual-path ``pick_option_expiration(symbol)``."""
    day = from_day or datetime.now(ET).date()
    _ = max_dte
    # Keep for call sites without a symbol: next session day (not forced 0DTE)
    if day.weekday() < 5:
        return day
    d = day
    for _ in range(10):
        d += timedelta(days=1)
        if d.weekday() < 5:
            return d
    return day + timedelta(days=1)


def _option_strike(spot: float, side: str, *, otm: float = 1.0) -> float:
    """1-point (or 1%) OTM strike for CALL/PUT; round to sensible increment."""
    px = max(float(spot), 0.01)
    side_u = (side or "CALL").upper()
    # Increment: $1 under $200, $5 for mega-priced names
    inc = 5.0 if px >= 500 else (1.0 if px >= 50 else 0.5)
    otm_pts = max(otm, inc) if px < 200 else max(otm, px * 0.005)

    def _round_down(x: float) -> float:
        return inc * int(x / inc)

    def _round_up(x: float) -> float:
        return inc * int((x + inc - 1e-9) / inc)

    if side_u in ("PUT", "SHORT", "BEAR", "BEARISH"):
        # long put slightly OTM
        return float(_round_down(px - otm_pts))
    # long call slightly OTM
    return float(_round_up(px + otm_pts))


def entry_from_multi_eval(
    result: TickerMultiEval,
    *,
    expires_at: str,
    trading_date: str,
    default_risk_pct: float = 1.0,
    cfg: MultiMethodConfig | None = None,
    require_export_quality: bool = True,
) -> Optional[Dict[str, Any]]:
    """Build one ENTER row from a PLAY multi-eval. None if incomplete or quality fail."""
    if not result.play or result.decision != "PLAY":
        return None
    if require_export_quality:
        if getattr(result, "export_eligible", False) is True:
            pass
        else:
            ok, _why = passes_export_quality(result, cfg=cfg or MultiMethodConfig())
            if not ok:
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
        contract_side = "CALL"
        strategy = f"Multi-method long call ({result.best_method})"
    elif side_raw in ("PUT", "SHORT", "BEAR", "BEARISH"):
        direction = "Bearish"
        contract_side = "PUT"
        strategy = f"Multi-method long put ({result.best_method})"
    else:
        # Neutral → skip options auto (need CALL/PUT)
        return None

    risk = _default_risk_dollars(entry, stop)
    methods = list(result.play_methods or [result.best_method])
    tags = ["multi_method", result.best_method, "options_debit", contract_side.lower()] + [
        m for m in methods if m != result.best_method
    ]
    # dedupe preserve order
    seen = set()
    method_tags = []
    for t in tags:
        if t and t not in seen:
            seen.add(t)
            method_tags.append(t)

    # Options package: single-leg debit around structure entry
    # Dual-path DTE: SPY/QQQ/IWM may be 0DTE; all others min DTE > 2 (default 3)
    from trading_agent.export.option_dte_policy import (
        dte_policy_label,
        pick_option_expiration,
    )

    strike = _option_strike(entry, contract_side)
    exp_day = pick_option_expiration(str(result.symbol or ""))
    exp_iso = exp_day.isoformat()
    dte = max(0, (exp_day - datetime.now(ET).date()).days)
    dte_policy = dte_policy_label(str(result.symbol or ""))

    thesis = (
        f"multi-method PLAY agg={result.aggregate_score:.0f}; "
        f"best={result.best_method} {contract_side}; methods={','.join(methods)}; "
        f"debit 1x {exp_iso} {strike}{contract_side[0]} dte={dte} policy={dte_policy}"
    )
    notes = "; ".join(result.reasons[:3])[:240]

    return {
        "symbol": result.symbol,
        "action": "ENTER",
        "side": direction,  # Bullish→CALL / Bearish→PUT via infer_call_put
        "instrument": "options",  # ALWAYS options — never share lots
        "strategy": strategy,
        "setup_id": f"multi_{result.best_method}",
        "setup_name": f"Multi-method: {result.best_method}",
        "setup_grade": "B" if result.aggregate_score >= 55 else "C",
        "grade_score": float(result.aggregate_score),
        "entry": round(entry, 4),  # underlying structure entry
        "stop": round(stop, 4),
        "target": round(target, 4),
        "strike_prices": [strike],
        "expiration": exp_iso,
        "max_risk_dollars": round(risk, 2),
        "max_reward_dollars": round(risk * 1.5, 2),
        "max_risk_pct": default_risk_pct,
        "confidence": min(95.0, 50.0 + result.aggregate_score * 0.4),
        "probability_of_success": 0.48,
        "technical_score": float(best.score),
        "fundamental_score": 0.0,
        "quality_score": float(
            getattr(result, "play_quality_score", 0) or result.aggregate_score
        ),
        "checklist_passed": True,
        "edge_complete": True,
        "auto_trade_eligible": True,
        "defined_risk": True,
        "options_strategy_class": f"long_{contract_side.lower()}",
        "dte": dte,
        "dte_policy": dte_policy,
        "mtf_note": "",
        "thesis": thesis[:400],
        "expires_at": expires_at,
        "notes": notes,
        "method_tags": method_tags,
        "method_notes": (
            f"source=multi_method_router; options_debit; play_methods={methods}; "
            f"playQ={getattr(result, 'play_quality_score', 0):.0f}/"
            f"{getattr(result, 'best_play_score', 0):.0f}; "
            f"strike={strike} exp={exp_iso}"
        )[:240],
        "stop_basis": "structure",
        "target_basis": "measured_move",
        "geometry_source": f"multi_method:{result.best_method}",
        "structure_notes": thesis[:240],
        "source": "multi_method_router",
        "trading_date": trading_date,
        "priority_boost": 5.0
        + len(methods) * 2.0
        + max(0.0, getattr(result, "best_play_score", 0) - 55.0) * 0.2,
        "quantity": 1,  # 1 contract
        "export_eligible": True,
        "play_quality_score": float(getattr(result, "play_quality_score", 0) or 0),
        "best_play_score": float(getattr(result, "best_play_score", 0) or 0),
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
    mm_cfg = MultiMethodConfig()
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
        ok_x, why_x = passes_export_quality(r, cfg=mm_cfg)
        if not ok_x and not getattr(r, "export_eligible", False):
            rejected.append(f"{r.symbol}:export_quality:{why_x}")
            continue
        row = entry_from_multi_eval(
            r, expires_at=expires, trading_date=trading_date, cfg=mm_cfg
        )
        if row is None:
            rejected.append(f"{r.symbol}:incomplete_or_quality")
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
        "scan_symbols": [str(getattr(r, "symbol", "")).upper() for r in results if getattr(r, "symbol", "")],
        "entry_count": len(entries),
        "rejected_incomplete": rejected[:60],
        "multi_method": {
            "play_count": len(play_syms),
            "play_symbols": list(play_syms),
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

    # Process cash bias: only suppress when explicitly requested (stay_in_cash=True)
    # or when auto-export is off and day bias is cash. Default multi-method path
    # (AUTO_EXPORT=1) does not empty the book just because research was cash.
    if stay_in_cash is None:
        auto = os.getenv("TRADING_AGENT_MULTI_METHOD_AUTO_EXPORT", "1").strip().lower() not in (
            "0",
            "false",
            "no",
            "off",
        )
        if not auto:
            try:
                from trading_agent.runbook.process import load_day_state

                st = load_day_state()
                if (st.bias or "").lower() == "cash":
                    stay_in_cash = True
            except Exception:
                pass
        else:
            stay_in_cash = False

    book = build_multi_method_book(
        results,
        merge_entries=merge_entries,
        stay_in_cash=stay_in_cash,
        regime=regime,
    )
    # Explicit cash suppress only when caller or (non-auto) process bias forced it
    if stay_in_cash is True:
        book["entries"] = []
        book["entry_count"] = 0
        book["stay_in_cash"] = True
        book["cash_reason"] = "process bias=cash — multi-method export suppressed"
        book["watchlist"] = []
    else:
        book["cio_required"] = False
        book["export_policy"] = "multi_method_auto_export_no_cio"

    paths = write_auto_trade_book(book, session_dir=session_dir, sync_dir=sync_dir)
    return book, paths
