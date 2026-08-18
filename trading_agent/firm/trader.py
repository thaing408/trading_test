"""P3 firm trader — BUY/SELL/HOLD from analysts + debate (+ optional book geometry).

Does not place orders. Optional merge into auto_trade_book when
TRADING_AGENT_FIRM_BOOK_MERGE=1 (still subject to OMS/DTE/cash later).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from trading_agent.firm.llm import chat_json, llm_enabled
from trading_agent.firm.reports import (
    DebateVerdict,
    FundamentalReport,
    NewsReport,
    ReportMeta,
    SentimentReport,
    TechnicalReport,
    TraderProposal,
)


def book_merge_enabled() -> bool:
    raw = os.getenv("TRADING_AGENT_FIRM_BOOK_MERGE", "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name, "1" if default else "0").strip().lower()
    if default:
        return raw not in ("0", "false", "no", "off")
    return raw in ("1", "true", "yes", "on")


def load_book_geometry(
    symbol: str,
    *,
    book_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Pull existing auto_trade_book row geometry for symbol if present."""
    paths: List[Path] = []
    if book_path:
        paths.append(Path(book_path))
    home = Path.home()
    paths.extend(
        [
            home / ".trading_agent" / "sync" / "auto_trade_book.json",
            home / ".grok" / "state" / "auto_trade_book.json",
        ]
    )
    sym = symbol.upper()
    for p in paths:
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for e in data.get("entries") or []:
            if not isinstance(e, dict):
                continue
            if str(e.get("symbol") or "").upper() != sym:
                continue
            return {
                "source_path": str(p),
                "action": e.get("action"),
                "side": e.get("side"),
                "entry": e.get("entry"),
                "stop": e.get("stop"),
                "target": e.get("target"),
                "strike_prices": e.get("strike_prices"),
                "expiration": e.get("expiration"),
                "max_risk_dollars": e.get("max_risk_dollars"),
                "dte": e.get("dte"),
                "dte_policy": e.get("dte_policy"),
                "setup_id": e.get("setup_id"),
                "strategy": e.get("strategy"),
                "confidence": e.get("confidence"),
                "thesis": e.get("thesis"),
                "instrument": e.get("instrument") or "options",
                "defined_risk": e.get("defined_risk", True),
            }
    return {}


def _heuristic_action(
    debate: DebateVerdict,
    tech: TechnicalReport,
    fund: FundamentalReport,
    sent: SentimentReport,
) -> Tuple[str, str, float, str, str]:
    """Return action, side, confidence, size_hint, timing."""
    winner = (debate.winner or "undecided").lower()
    conf = float(debate.confidence or 0)
    fund_s = float(fund.fundamental_score or 0)
    tech_bias = (tech.bias or "neutral").lower()

    # Hard soft-holds
    if any("earnings" in r.lower() and "(-20)" in r for r in (fund.reasons or [])):
        return (
            "HOLD",
            "",
            max(conf * 0.5, 25.0),
            "flat_or_min_until_post_print",
            "wait_event",
        )

    if winner == "bull" and conf >= 55 and tech_bias != "bearish":
        size = "full" if conf >= 70 and fund_s >= 60 else "half"
        timing = tech.entry_timing or "on_pullback"
        return "BUY", "Bullish", min(95.0, conf), size, timing

    if winner == "bear" and conf >= 55 and tech_bias != "bullish":
        size = "full" if conf >= 70 else "half"
        timing = tech.exit_timing or "on_bounce_fail"
        return "SELL", "Bearish", min(95.0, conf), size, timing

    if winner == "draw":
        # lean with tech if strong fund
        if tech_bias == "bullish" and fund_s >= 65 and sent.tilt != "bearish":
            return "BUY", "Bullish", 48.0, "probe", tech.entry_timing or "wait_confirm"
        if tech_bias == "bearish" and sent.tilt != "bullish":
            return "SELL", "Bearish", 48.0, "probe", tech.exit_timing or "wait_confirm"

    return "HOLD", "", max(conf * 0.6, 30.0), "no_new_risk", "stand_aside"


def _build_thesis(
    *,
    action: str,
    debate: DebateVerdict,
    tech: TechnicalReport,
    fund: FundamentalReport,
    news: NewsReport,
    sent: SentimentReport,
    geometry: Dict[str, Any],
) -> str:
    parts = [
        f"Firm trader → {action} after debate **{debate.winner}** "
        f"(conf {debate.confidence:.0f}).",
        f"Tech {tech.bias}/{tech.regime}; fund_score={fund.fundamental_score:.0f}; "
        f"sent={sent.tilt} ({sent.score:+.0f}).",
    ]
    if debate.bull_points:
        parts.append(f"Bull: {debate.bull_points[0]}")
    if debate.bear_points:
        parts.append(f"Bear: {debate.bear_points[0]}")
    if debate.open_risks:
        parts.append(f"Open risk: {debate.open_risks[0]}")
    if geometry.get("expiration"):
        parts.append(
            f"Book geometry: stop={geometry.get('stop')} tgt={geometry.get('target')} "
            f"exp={geometry.get('expiration')} dte={geometry.get('dte')}"
        )
    cat = (news.name_catalysts or news.headlines or [""])[0]
    if cat:
        parts.append(f"News: {cat[:120]}")
    parts.append("Rails: advisory only — OMS/DTE/cash still bind.")
    return " ".join(parts)[:600]


def build_trader_proposal(
    *,
    symbol: str,
    trading_date: str,
    tech: TechnicalReport,
    news: NewsReport,
    fund: FundamentalReport,
    sent: SentimentReport,
    debate: DebateVerdict,
    geometry: Optional[Dict[str, Any]] = None,
    use_llm: bool = True,
) -> TraderProposal:
    """Synthesize BUY/SELL/HOLD proposal (P3)."""
    sym = symbol.upper()
    geometry = geometry or {}
    action, side, confidence, size_hint, timing = _heuristic_action(
        debate, tech, fund, sent
    )
    thesis = _build_thesis(
        action=action,
        debate=debate,
        tech=tech,
        fund=fund,
        news=news,
        sent=sent,
        geometry=geometry,
    )

    # Prefer existing book side/instrument when proposing BUY that matches geometry
    instrument = str(geometry.get("instrument") or "options")
    defined_risk = bool(geometry.get("defined_risk", True))
    book_hints: Dict[str, Any] = {
        "mapped_action": {
            "BUY": "ENTER",
            "SELL": "EXIT_OR_ENTER_PUT",
            "HOLD": "SKIP",
        }.get(action, "SKIP"),
        "debate_winner": debate.winner,
        "debate_confidence": debate.confidence,
        "geometry": {
            k: geometry.get(k)
            for k in (
                "entry",
                "stop",
                "target",
                "strike_prices",
                "expiration",
                "max_risk_dollars",
                "dte",
                "dte_policy",
                "setup_id",
            )
            if geometry.get(k) is not None
        },
        "react_reasoning": [
            f"thought: weigh debate={debate.winner} vs tech={tech.bias} fund={fund.fundamental_score:.0f}",
            f"observation: open_risks={debate.open_risks[:3]}",
            f"act: propose {action} size={size_hint} timing={timing}",
        ],
    }
    if side and geometry.get("side") and action == "BUY":
        # keep bullish/bearish consistent with geometry when present
        book_hints["geometry_side"] = geometry.get("side")

    prop = TraderProposal(
        meta=ReportMeta(
            symbol=sym,
            trading_date=trading_date,
            role="trader",
            status="stub",
        ),
        action=action,
        side=side or str(geometry.get("side") or ""),
        size_hint=size_hint,
        timing=timing,
        confidence=float(confidence),
        thesis=thesis,
        book_hints=book_hints,
        instrument=instrument,
        defined_risk=defined_risk,
    )

    if use_llm and llm_enabled():
        sys = (
            "You are the desk trader. Given analyst reports and a debate verdict, "
            "return ONLY JSON with keys: action (BUY|SELL|HOLD), side (Bullish|Bearish|\"\"), "
            "size_hint, timing, confidence (0-100), thesis. "
            "Respect options/defined-risk context. Do not claim to bypass risk rails."
        )
        user = (
            f"Symbol {sym}\n"
            f"Debate winner={debate.winner} conf={debate.confidence}\n"
            f"Bull={debate.bull_points[:3]}\nBear={debate.bear_points[:3]}\n"
            f"Tech={tech.bias}/{tech.regime} entry={tech.entry_timing}\n"
            f"Fund score={fund.fundamental_score} reasons={fund.reasons[:3]}\n"
            f"Sent={sent.tilt} ({sent.score})\n"
            f"News={ (news.name_catalysts or news.headlines or [])[:2] }\n"
            f"Geometry={book_hints.get('geometry')}\n"
            f"Heuristic proposal={action}/{side}/{size_hint}"
        )
        llm = chat_json(sys, user, deep=True)
        if llm.get("ok") and isinstance(llm.get("data"), dict):
            d = llm["data"]
            a = str(d.get("action") or action).upper().strip()
            if a in ("BUY", "SELL", "HOLD"):
                prop.action = a
            prop.side = str(d.get("side") or prop.side)
            prop.size_hint = str(d.get("size_hint") or prop.size_hint)
            prop.timing = str(d.get("timing") or prop.timing)
            try:
                prop.confidence = float(d.get("confidence") or prop.confidence)
            except (TypeError, ValueError):
                pass
            if d.get("thesis"):
                prop.thesis = str(d["thesis"])[:600]
            prop.meta.status = "complete"
            prop.meta.model = str(llm.get("model") or "")
            prop.book_hints["mapped_action"] = {
                "BUY": "ENTER",
                "SELL": "EXIT_OR_ENTER_PUT",
                "HOLD": "SKIP",
            }.get(prop.action, "SKIP")
            prop.book_hints["react_reasoning"].append(
                f"llm_refine: {prop.action} conf={prop.confidence:.0f}"
            )

    if prop.meta.status == "empty":
        prop.meta.status = "stub"
    return prop


def proposal_to_book_fields(prop: TraderProposal) -> Dict[str, Any]:
    """Map TraderProposal → auto_trade_book-compatible field patch."""
    mapped = (prop.book_hints or {}).get("mapped_action") or "SKIP"
    geo = (prop.book_hints or {}).get("geometry") or {}
    action = "ENTER" if prop.action == "BUY" else (
        "EXIT" if prop.action == "SELL" else "HOLD"
    )
    # SELL on options desk usually means put ENTER or manage exit — keep explicit
    if prop.action == "SELL" and prop.side.lower() in ("bearish", "put"):
        action = "ENTER"
        side = "Bearish"
    elif prop.action == "BUY":
        side = prop.side or "Bullish"
    else:
        side = prop.side or ""
        action = "HOLD"

    out: Dict[str, Any] = {
        "symbol": prop.meta.symbol,
        "action": action if action != "HOLD" else "HOLD",
        "side": side,
        "instrument": prop.instrument or "options",
        "defined_risk": prop.defined_risk,
        "confidence": prop.confidence,
        "thesis": prop.thesis,
        "notes": f"firm_trader:{prop.action} size={prop.size_hint} timing={prop.timing}",
        "source": "firm_trader",
        "firm_action": prop.action,
        "firm_size_hint": prop.size_hint,
        "firm_timing": prop.timing,
        "firm_mapped": mapped,
        "auto_trade_eligible": prop.action == "BUY"
        or (prop.action == "SELL" and side == "Bearish"),
        "checklist_passed": prop.action != "HOLD",
        "fundamental_score": None,  # filled by caller if desired
    }
    # Preserve geometry when present
    for k in (
        "entry",
        "stop",
        "target",
        "strike_prices",
        "expiration",
        "max_risk_dollars",
        "dte",
        "dte_policy",
        "setup_id",
    ):
        if geo.get(k) is not None:
            out[k] = geo[k]
    if action == "HOLD":
        out["auto_trade_eligible"] = False
        out["checklist_passed"] = False
    return out


def maybe_merge_proposal_into_book(
    prop: TraderProposal,
    *,
    book_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Optionally patch sync auto_trade_book entry for symbol (fail-open).

    Controlled by TRADING_AGENT_FIRM_BOOK_MERGE=1. Never deletes other entries.
    HOLD → marks matching ENTER as not eligible (soft). BUY → upserts fields.
    """
    if not book_merge_enabled():
        return {"skipped": True, "reason": "TRADING_AGENT_FIRM_BOOK_MERGE=0"}

    path = Path(book_path) if book_path else (
        Path.home() / ".trading_agent" / "sync" / "auto_trade_book.json"
    )
    if not path.is_file():
        return {"ok": False, "error": "book_missing", "path": str(path)}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc)}

    entries = list(data.get("entries") or [])
    sym = prop.meta.symbol.upper()
    patch = proposal_to_book_fields(prop)
    found = False
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            continue
        if str(e.get("symbol") or "").upper() != sym:
            continue
        found = True
        if prop.action == "HOLD":
            e = dict(e)
            e["firm_trader_hold"] = True
            e["auto_trade_eligible"] = False
            e["notes"] = ((e.get("notes") or "") + f"; firm HOLD: {prop.thesis[:120]}")[:240]
            e["firm_action"] = "HOLD"
            entries[i] = e
        else:
            e = dict(e)
            for k, v in patch.items():
                if v is None:
                    continue
                if k in ("symbol",):
                    continue
                # Don't wipe strikes/exp if patch missing them
                if k in ("strike_prices", "expiration", "entry", "stop", "target") and not v:
                    continue
                e[k] = v
            if prop.action == "BUY" and e.get("action") != "ENTER":
                e["action"] = "ENTER"
            e["fundamental_score"] = e.get("fundamental_score")  # leave unless set
            entries[i] = e
        break

    if not found and prop.action == "BUY":
        # Only add if we have geometry — otherwise skip inventing a naked ENTER
        geo = (prop.book_hints or {}).get("geometry") or {}
        if geo.get("expiration") and geo.get("strike_prices"):
            row = proposal_to_book_fields(prop)
            row["action"] = "ENTER"
            row["strategy"] = row.get("strategy") or "Firm trader long"
            row["setup_id"] = row.get("setup_id") or "firm_trader"
            entries.append(row)
            found = True
        else:
            return {
                "ok": True,
                "merged": False,
                "reason": "no_geometry_to_create_enter",
                "path": str(path),
            }

    data["entries"] = entries
    data["entry_count"] = len([e for e in entries if isinstance(e, dict)])
    data["firm_trader_updated"] = prop.meta.symbol
    try:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "merged": found,
        "path": str(path),
        "firm_action": prop.action,
        "mapped": patch.get("firm_mapped"),
    }
