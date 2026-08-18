"""Firm sleeve runner (P0): empty structured reports + ReAct stubs.

When TRADING_AGENT_FIRM=0 (default): no-op, returns skipped.
When enabled: writes sessions/{date}/firm/{symbol}/ artifacts without LLM.
CIO / auto_trade_book are **unchanged**.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from zoneinfo import ZoneInfo

from trading_agent.firm.protocol import FirmCard, FirmMessage
from trading_agent.firm.react import analyst_stub_react_pass
from trading_agent.firm.roles import FIRM_ROLES
from trading_agent.firm.state import (
    FirmSymbolState,
    append_message,
    firm_enabled,
    firm_symbol_dir,
    init_empty_reports,
    persist_symbol_run,
)

ET = ZoneInfo("America/New_York")


def _trading_date(d: Optional[date] = None) -> str:
    if d is not None:
        return d.isoformat()
    return datetime.now(ET).date().isoformat()


def _max_symbols() -> int:
    try:
        return max(1, int(os.getenv("TRADING_AGENT_FIRM_MAX_SYMBOLS", "5") or 5))
    except ValueError:
        return 5


def run_firm_for_symbol(
    symbol: str,
    *,
    trading_date: Optional[str] = None,
    session_root: Optional[Path] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Build empty firm artifacts for one symbol.

    ``force=True`` writes even when TRADING_AGENT_FIRM=0 (CLI/fixture use).
    """
    sym = str(symbol or "").strip().upper()
    if not sym:
        return {"ok": False, "error": "empty_symbol"}
    day = trading_date or _trading_date()
    enabled = firm_enabled()
    if not enabled and not force:
        return {
            "ok": True,
            "skipped": True,
            "reason": "TRADING_AGENT_FIRM=0",
            "symbol": sym,
            "trading_date": day,
        }

    state = FirmSymbolState(
        symbol=sym,
        trading_date=day,
        status="running",
        flag_enabled=enabled or force,
        roles={name: role.to_dict() for name, role in FIRM_ROLES.items()},
    )
    reports = init_empty_reports(sym, day)

    # P0 ReAct stubs for analyst roles only
    for role_name in (
        "fundamental_analyst",
        "sentiment_analyst",
        "news_analyst",
        "technical_analyst",
    ):
        role = FIRM_ROLES[role_name]
        analyst_stub_react_pass(
            role_name,
            sym,
            list(role.allowed_tools),
            log=state.react_log,
        )
        append_message(
            state,
            FirmMessage(
                kind="react",
                role=role_name,
                symbol=sym,
                trading_date=day,
                payload={"tools": list(role.allowed_tools), "mode": "stub"},
            ),
        )

    card = FirmCard(
        symbol=sym,
        trading_date=day,
        fundamental_bullet="empty (P0)",
        sentiment_bullet="empty (P0)",
        news_bullet="empty (P0)",
        technical_bullet="empty (P0)",
        debate_winner="undecided",
        trader_action="HOLD",
        risk_adjustment="unchanged",
        manager_decision="defer",
        status="empty",
    )
    state.card = card.to_dict()
    state.status = "complete"
    out_dir = persist_symbol_run(state, reports, session_root=session_root)
    return {
        "ok": True,
        "skipped": False,
        "symbol": sym,
        "trading_date": day,
        "path": str(out_dir),
        "status": state.status,
        "react_steps": len(state.react_log),
        "card": state.card,
    }


def run_firm_sleeve(
    symbols: Sequence[str],
    *,
    trading_date: Optional[str] = None,
    session_root: Optional[Path] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Run firm P0 for a shortlist (capped). No-op when flag off unless force."""
    enabled = firm_enabled()
    day = trading_date or _trading_date()
    if not enabled and not force:
        return {
            "ok": True,
            "skipped": True,
            "reason": "TRADING_AGENT_FIRM=0",
            "trading_date": day,
            "symbols": [],
            "results": [],
        }

    capped = []
    seen = set()
    for s in symbols:
        u = str(s or "").strip().upper()
        if not u or u in seen:
            continue
        seen.add(u)
        capped.append(u)
        if len(capped) >= _max_symbols():
            break

    results = [
        run_firm_for_symbol(
            sym, trading_date=day, session_root=session_root, force=True
        )
        for sym in capped
    ]
    # Index file for the day
    root = Path(session_root) if session_root else Path.home() / ".trading_agent" / "sessions"
    index_dir = root / day / "firm"
    index_dir.mkdir(parents=True, exist_ok=True)
    index = {
        "schema_version": "firm_day_index_v1",
        "trading_date": day,
        "enabled": enabled or force,
        "symbols": capped,
        "results": [
            {"symbol": r.get("symbol"), "path": r.get("path"), "status": r.get("status")}
            for r in results
            if r.get("ok") and not r.get("skipped")
        ],
    }
    from trading_agent.firm.state import write_json

    write_json(index_dir / "index.json", index)
    return {
        "ok": True,
        "skipped": False,
        "trading_date": day,
        "symbols": capped,
        "results": results,
        "index_path": str(index_dir / "index.json"),
    }


def maybe_run_firm_after_research(
    symbols: Sequence[str],
    *,
    session_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Orchestrator hook — safe no-op when flag off."""
    if not firm_enabled():
        return {"ok": True, "skipped": True, "reason": "TRADING_AGENT_FIRM=0"}
    session_root = None
    trading_date = None
    if session_dir is not None:
        # session_dir is .../sessions/YYYY-MM-DD
        trading_date = session_dir.name
        session_root = session_dir.parent
    return run_firm_sleeve(
        symbols,
        trading_date=trading_date,
        session_root=session_root,
        force=False,
    )
