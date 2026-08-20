"""Export executable auto-trade book for macOS TOS / MCP consumer."""

from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from trading_agent.models import DailyTradingPlan, TradeOpportunity


def _load_day_bias_sidecar():
    """Optional local day-bias JSON (fail-closed if missing/invalid)."""
    from trading_agent.analysis.day_bias import DayBiasResult

    raw_path = os.getenv("TRADING_AGENT_DAY_BIAS_FILE", "").strip()
    candidates = []
    if raw_path:
        candidates.append(Path(raw_path))
    candidates.append(Path.home() / ".trading_agent" / "sync" / "day_bias.json")
    candidates.append(Path.home() / ".trading_agent" / "sync" / "day_bias_latest.json")
    for path in candidates:
        try:
            if not path.is_file():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            return DayBiasResult(
                bias=str(data.get("bias") or "neutral"),
                consecutive_up=int(data.get("consecutive_up") or 0),
                consecutive_down=int(data.get("consecutive_down") or 0),
                three_up_open=bool(data.get("three_up_open")),
                three_down_open=bool(data.get("three_down_open")),
                pdl=data.get("pdl"),
                pdh=data.get("pdh"),
                last=data.get("last"),
                above_pdl=data.get("above_pdl"),
                below_pdh=data.get("below_pdh"),
                valid=bool(data.get("valid")),
                tags=list(data.get("tags") or []),
                note=str(data.get("note") or ""),
                session=str(data.get("session") or ""),
            )
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
    return None


def default_sync_dir() -> Path:
    raw = os.getenv("TRADING_AGENT_SYNC_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    state = os.getenv("TRADING_AGENT_STATE_DIR", "").strip()
    if state:
        return Path(state).expanduser() / "sync"
    return Path.home() / ".trading_agent" / "sync"


def _entry_from_opp(opp: TradeOpportunity, *, expires_at: str) -> Dict[str, Any]:
    risk_pct = 0.0
    try:
        # Prefer explicit max risk if portfolio known later
        risk_pct = float(os.getenv("TRADING_AGENT_DEFAULT_RISK_PCT", "1.0"))
    except ValueError:
        risk_pct = 1.0
    return {
        "symbol": opp.symbol,
        "action": "ENTER",
        "side": opp.direction or "Neutral",
        "strategy": opp.strategy,
        "setup_id": getattr(opp, "playbook_setup_id", "") or "",
        "setup_name": getattr(opp, "playbook_name", "") or "",
        "setup_grade": opp.setup_grade,
        "grade_score": opp.grade_score,
        "entry": opp.entry_price,
        "stop": opp.stop_loss,
        "target": opp.profit_target,
        "strike_prices": list(opp.strike_prices or []),
        "expiration": opp.expiration,
        "max_risk_dollars": opp.maximum_risk,
        "max_reward_dollars": opp.maximum_reward,
        "max_risk_pct": risk_pct,
        "confidence": opp.confidence_score,
        "probability_of_success": opp.probability_of_success,
        "technical_score": getattr(opp.technical, "score", 0.0) if opp.technical else 0.0,
        "fundamental_score": float(getattr(opp, "fundamental_score", 0.0) or 0.0),
        "quality_score": float(
            getattr(opp, "combined_quality_score", None)
            or opp.trade_quality_score
            or 0.0
        ),
        "checklist_passed": bool(getattr(opp, "checklist_passed", False)),
        "edge_complete": bool(getattr(opp, "edge_complete", False)),
        "mtf_note": getattr(opp, "mtf_gate_reason", "") or "",
        "thesis": (opp.trade_thesis or "")[:400],
        "expires_at": expires_at,
        "notes": (getattr(opp, "checklist_summary", "") or "")[:240],
        # Brandt LFD / TechCharts structure (prefer over hardcoded %)
        "stop_basis": str(getattr(opp, "stop_basis", "") or ""),
        "target_basis": str(getattr(opp, "target_basis", "") or ""),
        "geometry_source": str(getattr(opp, "geometry_source", "") or ""),
        "risk_policy": str(getattr(opp, "risk_policy", "") or ""),
        "lfd_level": float(getattr(opp, "lfd_level", 0) or 0),
        "breakout_level": float(getattr(opp, "breakout_level", 0) or 0),
        "negation_level": float(getattr(opp, "negation_level", 0) or 0),
        "measured_target": float(getattr(opp, "measured_target", 0) or 0),
        "pattern_height": float(getattr(opp, "pattern_height", 0) or 0),
        "structure_notes": str(getattr(opp, "structure_notes", "") or "")[:240],
    }


def build_auto_trade_book(
    plan: DailyTradingPlan,
    *,
    min_grade: str = "B",
    require_checklist: bool = True,
    require_edge: bool = True,
    min_fundamental_score: float = 0.0,
    min_quality_score: float = 0.0,
    source_host: str | None = None,
) -> Dict[str, Any]:
    """Filter plan opportunities into Mac-executable ENTER rows."""
    from trading_agent.ranking.grades import GRADE_RANK

    min_rank = GRADE_RANK.get(min_grade, GRADE_RANK["B"])
    now = datetime.now(timezone.utc)
    expires = now.replace(hour=23, minute=59, second=0, microsecond=0).isoformat()
    entries: List[Dict[str, Any]] = []

    rejected_incomplete: List[str] = []
    for opp in plan.ranked_opportunities:
        g = opp.setup_grade or "C"
        if GRADE_RANK.get(g, 99) > min_rank:
            continue
        if require_checklist and not getattr(opp, "checklist_passed", False):
            rejected_incomplete.append(f"{opp.symbol}:checklist")
            continue
        if require_edge and not getattr(opp, "edge_complete", False):
            rejected_incomplete.append(f"{opp.symbol}:edge")
            continue
        # Fail closed: incomplete risk package never becomes ENTER
        if not (
            float(opp.entry_price or 0) > 0
            and float(opp.stop_loss or 0) > 0
            and float(opp.profit_target or 0) > 0
            and float(opp.stop_loss) != float(opp.profit_target)
            and float(opp.maximum_risk or 0) > 0
        ):
            rejected_incomplete.append(f"{opp.symbol}:incomplete_risk_package")
            continue
        # Prefer structure-backed stops for auto ENTER (LFD/negation/S-R, not pure ATR %)
        basis = str(getattr(opp, "stop_basis", "") or "").lower()
        geom = str(getattr(opp, "geometry_source", "") or "").lower()
        # Optional hard gate: set TRADING_AGENT_REQUIRE_STRUCTURE_STOP=1 to reject pure ATR %
        require_structure = os.getenv("TRADING_AGENT_REQUIRE_STRUCTURE_STOP", "0").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if require_structure and basis in ("", "atr") and (
            not getattr(opp, "lfd_level", 0) and not getattr(opp, "breakout_level", 0)
        ):
            rejected_incomplete.append(f"{opp.symbol}:no_structure_stop")
            continue
        if getattr(opp, "auto_trade_eligible", True) is False:
            rejected_incomplete.append(f"{opp.symbol}:not_auto_eligible")
            continue
        fund = float(getattr(opp, "fundamental_score", 0.0) or 0.0)
        if min_fundamental_score > 0 and fund < min_fundamental_score:
            rejected_incomplete.append(f"{opp.symbol}:fundamentals")
            continue
        qual = float(
            getattr(opp, "combined_quality_score", None) or opp.trade_quality_score or 0.0
        )
        if min_quality_score > 0 and qual < min_quality_score:
            rejected_incomplete.append(f"{opp.symbol}:quality")
            continue
        row = _entry_from_opp(opp, expires_at=expires)
        # Double-check ENTER payload integrity
        if not (
            row["entry"] > 0
            and row["stop"] > 0
            and row["target"] > 0
            and row["max_risk_dollars"] > 0
        ):
            rejected_incomplete.append(f"{opp.symbol}:enter_payload")
            continue
        row["method_tags"] = list(getattr(opp, "method_tags", None) or [])
        row["method_notes"] = str(getattr(opp, "method_notes", "") or "")[:240]
        # ADR extension tags (optional size cut when TRADING_AGENT_ADR_EXTENSION=1)
        try:
            from trading_agent.analysis.extension import try_enrich_entry_from_market

            row = try_enrich_entry_from_market(row)
        except Exception:  # noqa: BLE001
            pass
        # EP vs breakout family (optional EP size cut when TRADING_AGENT_EP_SLOW=1)
        try:
            from trading_agent.analysis.setup_family import apply_setup_family_to_entry

            row = apply_setup_family_to_entry(row)
        except Exception:  # noqa: BLE001
            pass
        # Researcher gap screener handoff (Raschke 4-day unfilled → continuation)
        try:
            from trading_agent.export.gap_book import apply_gap_boost_to_opportunity_fields, load_gap_book

            gap_book = load_gap_book()
            tags, _, gap_note = apply_gap_boost_to_opportunity_fields(
                symbol=opp.symbol,
                method_tags=row["method_tags"],
                auto_trade_eligible=bool(getattr(opp, "auto_trade_eligible", False)),
                book=gap_book,
            )
            row["method_tags"] = tags
            if gap_note:
                row["gap_screener"] = gap_note
                row["method_notes"] = (row["method_notes"] + "; " + gap_note).strip("; ")[:240]
            # Optional: require continuation tag for ENTER when env set
            require_gap = os.getenv("TRADING_AGENT_REQUIRE_GAP_CONTINUATION", "0").strip().lower() in (
                "1",
                "true",
                "yes",
            )
            if require_gap and "gap_continuation_4d" not in tags:
                rejected_incomplete.append(f"{opp.symbol}:not_gap_continuation")
                continue
            # Soft prefer: bump quality metadata for ranking on Mac side
            if "gap_continuation_4d" in tags:
                row["gap_continuation"] = True
                row["priority_boost"] = float(row.get("priority_boost") or 0) + 10.0
        except Exception:
            pass
        # Raschke first-30m 3-up + PDL day bias (optional local JSON or plan metadata)
        try:
            from trading_agent.analysis.day_bias import DayBiasResult, apply_day_bias_tags

            day_bias_meta = getattr(plan, "day_bias", None) or {}
            if isinstance(day_bias_meta, DayBiasResult):
                db = day_bias_meta
            elif isinstance(day_bias_meta, dict) and day_bias_meta:
                db = DayBiasResult(
                    bias=str(day_bias_meta.get("bias") or "neutral"),
                    consecutive_up=int(day_bias_meta.get("consecutive_up") or 0),
                    consecutive_down=int(day_bias_meta.get("consecutive_down") or 0),
                    three_up_open=bool(day_bias_meta.get("three_up_open")),
                    three_down_open=bool(day_bias_meta.get("three_down_open")),
                    pdl=day_bias_meta.get("pdl"),
                    pdh=day_bias_meta.get("pdh"),
                    last=day_bias_meta.get("last"),
                    above_pdl=day_bias_meta.get("above_pdl"),
                    below_pdh=day_bias_meta.get("below_pdh"),
                    valid=bool(day_bias_meta.get("valid")),
                    tags=list(day_bias_meta.get("tags") or []),
                    note=str(day_bias_meta.get("note") or ""),
                )
            else:
                db = _load_day_bias_sidecar()
            if db is not None and (db.valid or db.tags):
                tags, db_note, boost = apply_day_bias_tags(
                    row["method_tags"],
                    db,
                    direction=str(row.get("side") or ""),
                )
                row["method_tags"] = tags
                row["day_bias"] = db.bias
                row["day_bias_pdl"] = db.pdl
                row["day_bias_consecutive_up"] = db.consecutive_up
                if db_note:
                    row["method_notes"] = (row["method_notes"] + "; " + db_note).strip("; ")[:240]
                if boost:
                    row["priority_boost"] = float(row.get("priority_boost") or 0) + boost
        except Exception:
            pass
        # Options package for Mac TOS execution
        row["instrument"] = "options"
        row["options_strategy_class"] = str(
            getattr(opp, "options_strategy_class", "") or ""
        )
        row["iv_rank"] = float(getattr(opp, "iv_rank", 0) or 0)
        row["pop"] = float(getattr(opp, "options_pop", 0) or opp.probability_of_success or 0)
        row["delta"] = float(getattr(opp, "options_delta", 0) or 0)
        row["dte"] = int(getattr(opp, "expiration_days", 0) or 0)
        row["defined_risk"] = bool(getattr(opp, "defined_risk", True))
        row["options_method_notes"] = str(
            getattr(opp, "options_method_notes", "") or ""
        )[:240]
        if not row["defined_risk"]:
            rejected_incomplete.append(f"{opp.symbol}:not_defined_risk")
            continue
        if not row["strike_prices"]:
            rejected_incomplete.append(f"{opp.symbol}:missing_strikes")
            continue
        entries.append(row)

    host = source_host or socket.gethostname()
    # Dynamic scan set for Mac auto-trade (entries first, then watchlist)
    scan_symbols: List[str] = []
    seen: set[str] = set()
    for row in entries:
        s = str(row.get("symbol") or "").upper()
        if s and s not in seen:
            seen.add(s)
            scan_symbols.append(s)
    for s in plan.top_watchlist or []:
        u = str(s).upper()
        if u and u not in seen:
            seen.add(u)
            scan_symbols.append(u)
    for o in plan.ranked_opportunities or []:
        u = str(getattr(o, "symbol", "") or "").upper()
        if u and u not in seen:
            seen.add(u)
            scan_symbols.append(u)

    # Book-level day bias snapshot (sidecar or plan metadata; fail-closed empty)
    book_day_bias: Dict[str, Any] = {}
    try:
        db_book = getattr(plan, "day_bias", None)
        if db_book is None:
            db_book = _load_day_bias_sidecar()
        if db_book is not None:
            if hasattr(db_book, "to_dict"):
                book_day_bias = db_book.to_dict()
            elif isinstance(db_book, dict):
                book_day_bias = dict(db_book)
    except Exception:
        book_day_bias = {}

    return {
        "schema_version": 1,
        "generated_at": now.isoformat(),
        "source_host": host,
        "role": "windows-research",
        "trading_date": plan.date,
        "regime": plan.overall_market_bias,
        "environment_score": plan.market_environment_score,
        "stay_in_cash": bool(plan.stay_in_cash) or len(entries) == 0,
        "cash_reason": plan.cash_recommendation_reason or "",
        "entries": entries,
        "exits": [],
        "watchlist": list(plan.top_watchlist or []),
        "scan_symbols": scan_symbols,
        "entry_count": len(entries),
        "rejected_incomplete": rejected_incomplete[:40],
        "day_bias": book_day_bias,
        "broker_boundary": (
            "windows-research-suggest-export-only; "
            "no TOS order placement on research host"
        ),
    }


def _entry_count(book: Dict[str, Any]) -> int:
    try:
        n = int(book.get("entry_count") or 0)
    except (TypeError, ValueError):
        n = 0
    entries = book.get("entries") or []
    if isinstance(entries, list) and len(entries) > n:
        return len(entries)
    return n if n > 0 else (len(entries) if isinstance(entries, list) else 0)


def _looks_like_export_book(book: Dict[str, Any]) -> bool:
    """True if book has ENTER rows worth keeping (multi-method or desk export)."""
    entries = book.get("entries") or []
    if not isinstance(entries, list) or not entries:
        return False
    for e in entries:
        if not isinstance(e, dict):
            continue
        if str(e.get("action") or "").upper() == "ENTER":
            return True
        tags = e.get("method_tags") or []
        blob = " ".join(str(t) for t in tags) if isinstance(tags, list) else str(tags)
        blob += " " + str(e.get("strategy") or "") + " " + str(e.get("setup_id") or "")
        low = blob.lower()
        if any(
            k in low
            for k in (
                "multi_method",
                "multi-method",
                "top_winners",
                "swing_daily",
                "soulz",
                "fvg",
                "options",
            )
        ):
            return True
    return bool(entries)


def protect_auto_trade_book_from_empty_overwrite(
    book: Dict[str, Any],
    *,
    sync_dir: Path | None = None,
) -> Dict[str, Any]:
    """Do not let discovery/cash empty books wipe multi-method ENTERs same day.

    When the new book has 0 entries (typically stay_in_cash capital preservation)
    and the on-disk book for the same trading_date already has ENTER rows, keep
    those entries and annotate the book. Disable with
    TRADING_AGENT_PROTECT_AUTO_TRADE_BOOK=0.
    """
    flag = os.getenv("TRADING_AGENT_PROTECT_AUTO_TRADE_BOOK", "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return book

    new_n = _entry_count(book)
    if new_n > 0:
        return book

    sync = Path(sync_dir) if sync_dir is not None else default_sync_dir()
    existing_path = sync / "auto_trade_book.json"
    if not existing_path.is_file():
        return book
    try:
        existing = json.loads(existing_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return book
    if not isinstance(existing, dict):
        return book

    td_new = str(book.get("trading_date") or "")
    td_old = str(existing.get("trading_date") or "")
    if td_new and td_old and td_new != td_old:
        return book
    if not _looks_like_export_book(existing):
        return book

    old_entries = list(existing.get("entries") or [])
    if not old_entries:
        return book

    # Archive the empty attempt for forensics
    try:
        arch = sync / "archive"
        arch.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%H%M%S")
        td = td_new or td_old or "unknown"
        (arch / f"auto_trade_book_empty_attempt_{td}_{stamp}.json").write_text(
            json.dumps(book, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass

    preserved = dict(book)
    preserved["entries"] = old_entries
    preserved["entry_count"] = len(old_entries)
    preserved["stay_in_cash"] = False
    preserved["cash_reason"] = ""
    preserved["empty_overwrite_blocked"] = True
    preserved["preserved_entry_count"] = len(old_entries)
    preserved["preserved_from_generated_at"] = existing.get("generated_at")
    preserved["empty_attempt_reason"] = str(book.get("cash_reason") or "")[:400]
    # Keep newer watchlist/scan when provided
    if not preserved.get("watchlist") and existing.get("watchlist"):
        preserved["watchlist"] = existing.get("watchlist")
    if not preserved.get("scan_symbols") and existing.get("scan_symbols"):
        preserved["scan_symbols"] = existing.get("scan_symbols")
    # Prefer richer regime string
    if existing.get("regime") and "multi-method" in str(existing.get("regime") or "").lower():
        preserved["regime"] = existing.get("regime")
    return preserved


def write_auto_trade_book(
    book: Dict[str, Any],
    *,
    session_dir: Path | None = None,
    sync_dir: Path | None = None,
) -> List[Path]:
    """Write book to session dir and sync dir (Mac pull path)."""
    paths: List[Path] = []
    sync = Path(sync_dir) if sync_dir is not None else default_sync_dir()
    book = protect_auto_trade_book_from_empty_overwrite(book, sync_dir=sync)
    payload = json.dumps(book, indent=2) + "\n"
    targets: List[Path] = []
    if session_dir is not None:
        targets.append(Path(session_dir) / "auto_trade_book.json")
    targets.append(sync / "auto_trade_book.json")
    # Mac auto-trade MCP reads ~/.grok/state as well
    grok_state = Path.home() / ".grok" / "state"
    targets.append(grok_state / "auto_trade_book.json")
    # Also date-stamped archive in sync
    td = book.get("trading_date") or "unknown"
    targets.append(sync / "archive" / f"auto_trade_book_{td}.json")

    for path in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
        paths.append(path)

    # Dedicated scan-symbols artifact for auto-trade / pulse (always refreshed)
    scan_syms = list(book.get("scan_symbols") or book.get("watchlist") or [])
    scan_payload = json.dumps(
        {
            "schema_version": 1,
            "trading_date": book.get("trading_date"),
            "updated_at": book.get("generated_at"),
            "symbols": scan_syms,
            "scan_symbols": scan_syms,
            "watchlist": list(book.get("watchlist") or []),
            "stay_in_cash": book.get("stay_in_cash"),
            "source": "trading_agent_export",
        },
        indent=2,
    ) + "\n"
    scan_targets = [
        sync / "auto_trade_scan_symbols.json",
        grok_state / "auto_trade_scan_symbols.json",
    ]
    if session_dir is not None:
        scan_targets.append(Path(session_dir) / "auto_trade_scan_symbols.json")
    for path in scan_targets:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(scan_payload, encoding="utf-8")
            paths.append(path)
        except OSError:
            continue
    # Canonical shared scanned list (trading_test + trading_agent same path)
    try:
        from trading_agent.export.scanned_list import merge_publish_from_book

        _, scan_paths = merge_publish_from_book(
            book,
            source_phase="auto_trade_book",
            session_dir=session_dir,
            sync_dir=sync,
        )
        paths.extend(scan_paths)
    except Exception:
        pass
    return paths


def export_plan_for_execution(
    plan: DailyTradingPlan,
    *,
    session_dir: Path | None = None,
    sync_dir: Path | None = None,
    min_grade: str = "B",
    min_fundamental_score: float = 45.0,
    min_quality_score: float = 55.0,
) -> Dict[str, Any]:
    book = build_auto_trade_book(
        plan,
        min_grade=min_grade,
        require_checklist=True,
        require_edge=True,
        min_fundamental_score=min_fundamental_score,
        min_quality_score=min_quality_score,
    )
    paths = write_auto_trade_book(book, session_dir=session_dir, sync_dir=sync_dir)
    book["_written_paths"] = [str(p) for p in paths]
    return book
