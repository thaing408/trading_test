"""Export executable auto-trade book for macOS TOS / MCP consumer."""

from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from trading_agent.models import DailyTradingPlan, TradeOpportunity


def default_sync_dir() -> Path:
    raw = os.getenv("TRADING_AGENT_SYNC_DIR", "").strip()
    if raw:
        return Path(raw)
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
        entries.append(row)

    host = source_host or socket.gethostname()
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
        "entry_count": len(entries),
        "rejected_incomplete": rejected_incomplete[:40],
        "broker_boundary": (
            "windows-research-suggest-export-only; "
            "no TOS order placement on research host"
        ),
    }


def write_auto_trade_book(
    book: Dict[str, Any],
    *,
    session_dir: Path | None = None,
    sync_dir: Path | None = None,
) -> List[Path]:
    """Write book to session dir and sync dir (Mac pull path)."""
    paths: List[Path] = []
    payload = json.dumps(book, indent=2) + "\n"
    targets: List[Path] = []
    if session_dir is not None:
        targets.append(Path(session_dir) / "auto_trade_book.json")
    sync = Path(sync_dir) if sync_dir is not None else default_sync_dir()
    targets.append(sync / "auto_trade_book.json")
    # Also date-stamped archive in sync
    td = book.get("trading_date") or "unknown"
    targets.append(sync / "archive" / f"auto_trade_book_{td}.json")

    for path in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
        paths.append(path)
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
