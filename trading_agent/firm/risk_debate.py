"""P4 risk trio (aggressive / neutral / conservative) + facilitator."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from trading_agent.firm.llm import chat_json, llm_enabled
from trading_agent.firm.reports import (
    DebateVerdict,
    FundamentalReport,
    ReportMeta,
    RiskAdjustment,
    TechnicalReport,
    TraderProposal,
)


def _oms_exposure_snapshot() -> Dict[str, Any]:
    try:
        from trading_agent.oms.state import OmsStore

        store = OmsStore()
        lots = list(store.open_lots())
        return {
            "open_lots": len(lots),
            "open_risk": float(store.open_risk_dollars()),
            "symbols": [l.symbol for l in lots][:20],
        }
    except Exception as exc:  # noqa: BLE001
        return {"open_lots": 0, "open_risk": 0.0, "symbols": [], "error": str(exc)}


def _persona_votes(
    prop: TraderProposal,
    tech: TechnicalReport,
    fund: FundamentalReport,
    debate: DebateVerdict,
    exposure: Dict[str, Any],
) -> Dict[str, str]:
    open_n = int(exposure.get("open_lots") or 0)
    open_risk = float(exposure.get("open_risk") or 0)
    earnings_hot = any("earnings" in r.lower() and "(-20)" in r for r in (fund.reasons or []))
    crowded = open_n >= 4 or open_risk >= 1200
    high_vol = float(getattr(tech, "indicator_highlights", None) and 0)  # unused
    adx_high = any("ADX=" in h and float(h.split("=")[-1]) >= 30 for h in (tech.indicator_highlights or []) if "ADX=" in h)

    aggressive = "increase"
    neutral = "unchanged"
    conservative = "cut_size"

    if prop.action == "HOLD":
        return {
            "aggressive": "unchanged",
            "neutral": "unchanged",
            "conservative": "unchanged",
        }

    if earnings_hot or crowded:
        aggressive = "cut_size"
        neutral = "cut_size"
        conservative = "veto"
    elif prop.confidence < 50 or debate.winner == "draw":
        aggressive = "unchanged"
        neutral = "cut_size"
        conservative = "tighten_stop"
    elif prop.action == "BUY" and prop.confidence >= 70 and fund.fundamental_score >= 70 and not crowded:
        aggressive = "increase"
        neutral = "unchanged"
        conservative = "cut_size"
    elif adx_high and prop.action == "BUY":
        aggressive = "unchanged"
        neutral = "tighten_stop"
        conservative = "cut_size"

    return {
        "aggressive": aggressive,
        "neutral": neutral,
        "conservative": conservative,
    }


def _facilitate(
    votes: Dict[str, str],
    prop: TraderProposal,
    fund: FundamentalReport,
    exposure: Dict[str, Any],
) -> Tuple[str, float, str, List[str]]:
    """Return recommendation, size_mult, stop_note, exposure_notes."""
    # Deterministic vetoes (last word)
    if any("earnings" in r.lower() and "(-20)" in r for r in (fund.reasons or [])):
        return "veto", 0.0, "earnings_hard_block", [
            "deterministic_veto:earnings_proximity",
            f"open_lots={exposure.get('open_lots')}",
        ]
    if int(exposure.get("open_lots") or 0) >= 5:
        return "veto", 0.0, "max_open_lots", [
            "deterministic_veto:max_open_lots",
            f"open_risk={exposure.get('open_risk')}",
        ]

    # Majority-ish: conservative veto wins if any; else prefer cut over increase
    vals = list(votes.values())
    if "veto" in vals:
        return "veto", 0.0, "risk_persona_veto", ["conservative_or_crowd_veto"]
    if vals.count("cut_size") >= 2:
        return "cut_size", 0.5, "reduce_size_half", [f"votes={votes}"]
    if vals.count("tighten_stop") >= 2:
        return "tighten_stop", 0.75, "tighten_stop_25pct_toward_entry", [f"votes={votes}"]
    if vals.count("increase") >= 2 and prop.confidence >= 70:
        return "increase", 1.25, "", [f"votes={votes}"]
    return "unchanged", 1.0, "", [f"votes={votes}"]


def run_risk_debate(
    *,
    symbol: str,
    trading_date: str,
    prop: TraderProposal,
    tech: TechnicalReport,
    fund: FundamentalReport,
    debate: DebateVerdict,
    use_llm: bool = True,
    exposure: Optional[Dict[str, Any]] = None,
) -> RiskAdjustment:
    exposure = exposure if exposure is not None else _oms_exposure_snapshot()
    votes = _persona_votes(prop, tech, fund, debate, exposure)
    rec, size_mult, stop_note, notes = _facilitate(votes, prop, fund, exposure)
    notes = list(notes) + [
        f"open_lots={exposure.get('open_lots')}",
        f"open_risk={exposure.get('open_risk')}",
        "hard_rails_respected=True",
    ]

    adj = RiskAdjustment(
        meta=ReportMeta(
            symbol=symbol.upper(),
            trading_date=trading_date,
            role="risk_facilitator",
            status="stub",
        ),
        recommendation=rec,
        size_mult=float(size_mult),
        stop_note=stop_note,
        exposure_notes=notes[:12],
        persona_votes=votes,
        hard_rails_respected=True,
    )

    if use_llm and llm_enabled() and rec != "veto":
        sys = (
            "You are the risk facilitator. Return ONLY JSON with keys: "
            "recommendation (increase|cut_size|tighten_stop|veto|unchanged), "
            "size_mult, stop_note, exposure_notes (array), persona_votes (object). "
            "Never remove hard earnings/open-lot vetoes if already veto."
        )
        user = (
            f"Symbol {symbol} trader={prop.action}/{prop.confidence} "
            f"debate={debate.winner} exposure={exposure} heuristic={adj.to_dict()}"
        )
        llm = chat_json(sys, user, deep=True)
        if llm.get("ok") and isinstance(llm.get("data"), dict):
            d = llm["data"]
            # Do not override hard veto
            if rec != "veto":
                r = str(d.get("recommendation") or rec)
                if r in ("increase", "cut_size", "tighten_stop", "veto", "unchanged"):
                    adj.recommendation = r
                try:
                    adj.size_mult = float(d.get("size_mult") or size_mult)
                except (TypeError, ValueError):
                    pass
                adj.stop_note = str(d.get("stop_note") or stop_note)
            if isinstance(d.get("exposure_notes"), list):
                adj.exposure_notes = [str(x) for x in d["exposure_notes"][:12]]
            if isinstance(d.get("persona_votes"), dict):
                adj.persona_votes = {str(k): str(v) for k, v in d["persona_votes"].items()}
            adj.meta.status = "complete"
            adj.meta.model = str(llm.get("model") or "")

    if adj.meta.status == "empty":
        adj.meta.status = "stub"
    return adj


def apply_risk_to_proposal(prop: TraderProposal, risk: RiskAdjustment) -> TraderProposal:
    """Mutate proposal size/timing/action from risk adjustment (still advisory)."""
    prop.book_hints = dict(prop.book_hints or {})
    prop.book_hints["risk_adjustment"] = risk.recommendation
    prop.book_hints["risk_size_mult"] = risk.size_mult
    if risk.recommendation == "veto":
        prop.action = "HOLD"
        prop.size_hint = "vetoed"
        prop.timing = "no_trade"
        prop.confidence = min(prop.confidence, 35.0)
        prop.thesis = (prop.thesis + f" | RISK VETO: {risk.stop_note}")[:600]
        prop.book_hints["mapped_action"] = "SKIP"
    elif risk.recommendation == "cut_size":
        prop.size_hint = f"half×{risk.size_mult:.2f}"
    elif risk.recommendation == "increase":
        prop.size_hint = f"full×{risk.size_mult:.2f}"
    elif risk.recommendation == "tighten_stop":
        prop.timing = (prop.timing or "") + "+tighten_stop"
        prop.book_hints["tighten_stop"] = risk.stop_note
    return prop
