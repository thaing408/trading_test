"""Firm sleeve runner.

P0: empty schemas when forced without analysts.
P1: live gathers + heuristic analyst reports (+ optional xAI LLM).

TRADING_AGENT_FIRM=0 (default): desk no-op.
CIO / auto_trade_book unchanged.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from zoneinfo import ZoneInfo

from trading_agent.firm.analysts import (
    build_fundamental_report,
    build_news_report,
    build_sentiment_report,
    build_technical_report,
)
from trading_agent.firm.debate import run_debate
from trading_agent.firm.protocol import FirmCard, FirmMessage
from trading_agent.firm.reports import (
    ManagerDecision,
    RiskAdjustment,
    TraderProposal,
)
from trading_agent.firm.roles import FIRM_ROLES
from trading_agent.firm.state import (
    FirmSymbolState,
    append_message,
    firm_enabled,
    persist_symbol_run,
    write_json,
)
from trading_agent.firm.tools import call_tool

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


def _use_llm() -> bool:
    raw = os.getenv("TRADING_AGENT_FIRM_LLM", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _bullet(text: str, n: int = 90) -> str:
    t = (text or "").strip().replace("\n", " ")
    return (t[: n - 1] + "…") if len(t) > n else t


def run_firm_for_symbol(
    symbol: str,
    *,
    trading_date: Optional[str] = None,
    session_root: Optional[Path] = None,
    force: bool = False,
    use_llm: Optional[bool] = None,
) -> Dict[str, Any]:
    """Run P1 analysts for one symbol (heuristics always; LLM if enabled)."""
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

    llm = _use_llm() if use_llm is None else bool(use_llm)

    state = FirmSymbolState(
        symbol=sym,
        trading_date=day,
        status="running",
        flag_enabled=enabled or force,
        roles={name: role.to_dict() for name, role in FIRM_ROLES.items()},
    )

    # --- ReAct gather (real tools) ---
    tool_cache: Dict[str, Any] = {}
    for role_name in (
        "fundamental_analyst",
        "sentiment_analyst",
        "news_analyst",
        "technical_analyst",
    ):
        role = FIRM_ROLES[role_name]
        for tool in role.allowed_tools:
            if tool in tool_cache:
                # still log reuse
                state.react_log.append(
                    {
                        "role": role_name,
                        "thought": f"reuse cached `{tool}` for {sym}",
                        "tool": tool,
                        "tool_args": {},
                        "observation": {"cached": True, "tool": tool},
                    }
                )
                continue
            from trading_agent.firm.react import react_call

            step = react_call(
                role_name,
                symbol=sym,
                thought=f"P1: gather `{tool}` for {sym}",
                tool=tool,
                log=state.react_log,
            )
            tool_cache[tool] = (step.observation or {}).get("data") or {}
        append_message(
            state,
            FirmMessage(
                kind="react",
                role=role_name,
                symbol=sym,
                trading_date=day,
                payload={"tools": list(role.allowed_tools), "mode": "p1_live"},
            ),
        )

    ohlcv = tool_cache.get("ohlcv") or call_tool("ohlcv", symbol=sym).data
    ta = tool_cache.get("ta_bundle") or call_tool("ta_bundle", symbol=sym).data
    news = tool_cache.get("news") or call_tool("news", symbol=sym).data
    fund = tool_cache.get("fundamentals") or call_tool("fundamentals", symbol=sym).data
    insider = tool_cache.get("insider") or call_tool("insider", symbol=sym).data
    social = tool_cache.get("social") or call_tool("social", symbol=sym).data

    # --- Analyst reports (P1) ---
    tech_r = build_technical_report(sym, day, ta, use_llm=llm)
    news_r = build_news_report(sym, day, news, use_llm=llm)
    fund_r = build_fundamental_report(sym, day, fund, insider, use_llm=llm)
    sent_r = build_sentiment_report(sym, day, social, use_llm=llm)

    # --- Researcher debate (P2) ---
    debate, debate_transcript = run_debate(
        symbol=sym,
        trading_date=day,
        tech=tech_r,
        news=news_r,
        fund=fund_r,
        sent=sent_r,
        use_llm=llm,
    )
    state.react_log.append(
        {
            "role": "debate_facilitator",
            "thought": "P2 bull/bear debate on analyst reports",
            "tool": "",
            "observation": {
                "winner": debate.winner,
                "confidence": debate.confidence,
                "rounds": debate.rounds,
            },
        }
    )
    append_message(
        state,
        FirmMessage(
            kind="debate",
            role="debate_facilitator",
            symbol=sym,
            trading_date=day,
            payload={"transcript": debate_transcript[-6:], "verdict": debate.to_dict()},
        ),
    )
    # Persist full transcript beside reports
    # (written after out_dir known — see below)

    # P3–P4 still stubs
    trader = TraderProposal.empty(sym, day)
    risk = RiskAdjustment.empty(sym, day)
    manager = ManagerDecision.empty(sym, day)

    reports = {
        "fundamental": fund_r.to_dict(),
        "sentiment": sent_r.to_dict(),
        "news": news_r.to_dict(),
        "technical": tech_r.to_dict(),
        "debate": debate.to_dict(),
        "trader": trader.to_dict(),
        "risk": risk.to_dict(),
        "manager": manager.to_dict(),
    }

    card = FirmCard(
        symbol=sym,
        trading_date=day,
        fundamental_bullet=_bullet(
            f"score={fund_r.fundamental_score:.0f} {fund_r.reasons[0] if fund_r.reasons else ''}"
        ),
        sentiment_bullet=_bullet(f"{sent_r.tilt} ({sent_r.score:+.0f})"),
        news_bullet=_bullet(
            (news_r.name_catalysts[0] if news_r.name_catalysts else "")
            or (news_r.headlines[0] if news_r.headlines else "no headlines")
        ),
        technical_bullet=_bullet(f"{tech_r.bias}/{tech_r.regime}"),
        debate_winner=debate.winner,
        debate_confidence=float(debate.confidence or 0),
        trader_action=trader.action,
        risk_adjustment=risk.recommendation,
        manager_decision=manager.decision,
        status="p2_debate",
    )
    state.card = card.to_dict()
    state.status = "complete"
    out_dir = persist_symbol_run(state, reports, session_root=session_root)
    write_json(
        Path(out_dir) / "debate_transcript.json",
        {
            "symbol": sym,
            "trading_date": day,
            "rounds": debate.rounds,
            "winner": debate.winner,
            "confidence": debate.confidence,
            "transcript": debate_transcript,
        },
    )
    return {
        "ok": True,
        "skipped": False,
        "symbol": sym,
        "trading_date": day,
        "path": str(out_dir),
        "status": state.status,
        "react_steps": len(state.react_log),
        "llm": llm,
        "analyst_status": {
            "technical": tech_r.meta.status,
            "news": news_r.meta.status,
            "fundamental": fund_r.meta.status,
            "sentiment": sent_r.meta.status,
            "fundamental_score": fund_r.fundamental_score,
        },
        "debate": {
            "winner": debate.winner,
            "confidence": debate.confidence,
            "rounds": debate.rounds,
            "status": debate.meta.status,
        },
        "card": state.card,
    }


def run_firm_sleeve(
    symbols: Sequence[str],
    *,
    trading_date: Optional[str] = None,
    session_root: Optional[Path] = None,
    force: bool = False,
    use_llm: Optional[bool] = None,
) -> Dict[str, Any]:
    """Run firm P1 for a shortlist (capped)."""
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

    capped: List[str] = []
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
            sym,
            trading_date=day,
            session_root=session_root,
            force=True,
            use_llm=use_llm,
        )
        for sym in capped
    ]
    root = Path(session_root) if session_root else Path.home() / ".trading_agent" / "sessions"
    index_dir = root / day / "firm"
    index_dir.mkdir(parents=True, exist_ok=True)
    index = {
        "schema_version": "firm_day_index_v1",
        "trading_date": day,
        "enabled": enabled or force,
        "phase": "P2_debate",
        "symbols": capped,
        "results": [
            {
                "symbol": r.get("symbol"),
                "path": r.get("path"),
                "status": r.get("status"),
                "analyst_status": r.get("analyst_status"),
            }
            for r in results
            if r.get("ok") and not r.get("skipped")
        ],
    }
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
        trading_date = session_dir.name
        session_root = session_dir.parent
    return run_firm_sleeve(
        symbols,
        trading_date=trading_date,
        session_root=session_root,
        force=False,
    )
