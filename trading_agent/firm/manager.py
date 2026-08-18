"""P4 fund manager overlay — final Approve/Modify/Reject/Defer for CIO handoff."""

from __future__ import annotations

from typing import Any, Dict, Optional

from trading_agent.firm.llm import chat_json, llm_enabled
from trading_agent.firm.reports import (
    DebateVerdict,
    ManagerDecision,
    ReportMeta,
    RiskAdjustment,
    TraderProposal,
)


def build_manager_decision(
    *,
    symbol: str,
    trading_date: str,
    prop: TraderProposal,
    risk: RiskAdjustment,
    debate: DebateVerdict,
    use_llm: bool = True,
) -> ManagerDecision:
    """CIO-facing decision. Deterministic vetoes already applied in risk layer."""
    if risk.recommendation == "veto" or prop.action == "HOLD":
        decision = "reject" if risk.recommendation == "veto" else "defer"
        notes = (
            f"Manager {decision}: trader={prop.action} risk={risk.recommendation} "
            f"({risk.stop_note or 'stand aside'})."
        )
        return ManagerDecision(
            meta=ReportMeta(
                symbol=symbol.upper(),
                trading_date=trading_date,
                role="fund_manager",
                status="stub",
            ),
            decision=decision,
            size_mult=0.0 if decision == "reject" else risk.size_mult,
            notes=notes,
            cites_debate_winner=debate.winner,
            cites_risk_adjustment=risk.recommendation,
            cio_handoff={
                "approve": False,
                "reason": notes,
                "firm_action": prop.action,
                "hard_rails": True,
            },
        )

    if risk.recommendation in ("cut_size", "tighten_stop"):
        decision = "modify"
        size_mult = float(risk.size_mult or 0.5)
        notes = (
            f"Manager modify: keep {prop.action} with size_mult={size_mult} "
            f"stop_note={risk.stop_note}."
        )
    elif risk.recommendation == "increase" and prop.confidence >= 70:
        decision = "approve"
        size_mult = float(risk.size_mult or 1.25)
        notes = f"Manager approve oversized lean: {prop.action} conf={prop.confidence:.0f}."
    else:
        decision = "approve"
        size_mult = float(risk.size_mult or 1.0)
        notes = (
            f"Manager approve: {prop.action}/{prop.side} size={prop.size_hint} "
            f"debate={debate.winner}."
        )

    dec = ManagerDecision(
        meta=ReportMeta(
            symbol=symbol.upper(),
            trading_date=trading_date,
            role="fund_manager",
            status="stub",
        ),
        decision=decision,
        size_mult=size_mult,
        notes=notes,
        cites_debate_winner=debate.winner,
        cites_risk_adjustment=risk.recommendation,
        cio_handoff={
            "approve": decision == "approve",
            "modify": decision == "modify",
            "reject": decision == "reject",
            "size_mult": size_mult,
            "firm_action": prop.action,
            "thesis": prop.thesis[:240],
            "hard_rails": True,
        },
    )

    if use_llm and llm_enabled() and decision in ("approve", "modify"):
        sys = (
            "You are the fund manager. Return ONLY JSON with keys: "
            "decision (approve|modify|reject|defer), size_mult, notes. "
            "Do not approve if risk recommendation is veto."
        )
        user = (
            f"{symbol} trader={prop.action} risk={risk.recommendation} "
            f"debate={debate.winner} heuristic_decision={decision}"
        )
        llm = chat_json(sys, user, deep=True)
        if llm.get("ok") and isinstance(llm.get("data"), dict):
            d = llm["data"]
            if risk.recommendation != "veto":
                dd = str(d.get("decision") or decision).lower()
                if dd in ("approve", "modify", "reject", "defer"):
                    dec.decision = dd
                try:
                    dec.size_mult = float(d.get("size_mult") or size_mult)
                except (TypeError, ValueError):
                    pass
            if d.get("notes"):
                dec.notes = str(d["notes"])[:400]
            dec.meta.status = "complete"
            dec.meta.model = str(llm.get("model") or "")
            dec.cio_handoff["approve"] = dec.decision == "approve"
            dec.cio_handoff["modify"] = dec.decision == "modify"
            dec.cio_handoff["reject"] = dec.decision == "reject"

    if dec.meta.status == "empty":
        dec.meta.status = "stub"
    return dec
