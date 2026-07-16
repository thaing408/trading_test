"""Persist desk session artifacts between phases."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date
from pathlib import Path
from typing import Any

from trading_agent.models import DailyTradingPlan
from trading_agent.regime import infer_market_regime
from trading_agent.session.intelligence import IntelligenceBrief


def plan_to_context(plan: DailyTradingPlan) -> dict:
    return {
        "date": plan.date,
        "overall_market_bias": plan.overall_market_bias,
        "market_environment_score": plan.market_environment_score,
        "market_regime": infer_market_regime(plan.overall_market_bias),
        "top_watchlist": plan.top_watchlist,
        "news_highlights": plan.research_summary.get("news_highlights", []),
        "high_impact_events": plan.research_summary.get("high_impact_events", []),
        "stay_in_cash": plan.stay_in_cash,
        "cash_recommendation_reason": plan.cash_recommendation_reason,
        "ranked_symbols": [opp.symbol for opp in plan.ranked_opportunities],
        "ranked_opportunities": [
            {
                "symbol": opp.symbol,
                "strategy": opp.strategy,
                "direction": opp.direction,
                "entry_price": opp.entry_price,
                "strike_prices": opp.strike_prices,
                "expiration": opp.expiration,
                "profit_target": opp.profit_target,
                "stop_loss": opp.stop_loss,
                "confidence_score": opp.confidence_score,
                "probability_of_success": opp.probability_of_success,
                "maximum_risk": opp.maximum_risk,
                "maximum_reward": opp.maximum_reward,
                "setup_grade": opp.setup_grade,
                "playbook_setup_id": getattr(opp, "playbook_setup_id", ""),
                "playbook_name": getattr(opp, "playbook_name", ""),
                "checklist_passed": getattr(opp, "checklist_passed", False),
                "edge_complete": getattr(opp, "edge_complete", False),
                "fundamental_score": getattr(opp, "fundamental_score", 0.0),
                "combined_quality_score": getattr(opp, "combined_quality_score", 0.0),
                "auto_trade_eligible": getattr(opp, "auto_trade_eligible", False),
            }
            for opp in plan.ranked_opportunities
        ],
        "rejection_reasons": [
            {"symbol": r.symbol, "reason": r.reason} for r in plan.rejection_reasons
        ],
        "auto_trade_symbols": _dedupe_symbols(
            [
                opp.symbol
                for opp in plan.ranked_opportunities
                if getattr(opp, "auto_trade_eligible", False)
            ]
            + list(plan.top_watchlist or [])
        ),
    }


def _dedupe_symbols(symbols: list) -> list:
    out: list = []
    seen: set = set()
    for s in symbols:
        u = str(s or "").strip().upper()
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def default_session_dir(trading_date: date, base: Path | None = None) -> Path:
    root = base or Path.home() / ".trading_agent" / "sessions"
    path = root / trading_date.isoformat()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    return path


def save_plan_context(context: dict, directory: Path) -> Path:
    return _write_json(directory / "daily_plan_context.json", context)


def load_saved_plan_context(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def save_intelligence(brief: IntelligenceBrief, directory: Path) -> Path:
    payload = {
        "date": brief.date,
        "bias": brief.bias,
        "environment_score": brief.environment_score,
        "outlook": brief.outlook,
        "market_posture": brief.market_posture,
        "overnight_summary": brief.overnight_summary,
        "market_signals": brief.market_signals,
        "calendar_summary": brief.calendar_summary,
        "high_impact_events": brief.high_impact_events,
        "news_highlights": brief.news_highlights,
        "catalyst_symbols": brief.catalyst_symbols,
        "sector_ranking": brief.sector_ranking,
        "etf_snapshot": brief.etf_snapshot,
        "breadth_notes": brief.breadth_notes,
        "top_opportunities": brief.top_opportunities,
        "major_risks": brief.major_risks,
        "expected_drivers": brief.expected_drivers,
        "unavailable_series": brief.unavailable_series,
        "vix_term_note": brief.vix_term_note,
        "yield_curve_note": brief.yield_curve_note,
        "errors": brief.errors,
        "metadata": brief.metadata,
    }
    return _write_json(directory / "intelligence.json", payload)


def load_intelligence(directory: Path) -> dict:
    path = directory / "intelligence.json"
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def save_cio_inputs(directory: Path, candidates: list, context: dict) -> Path:
    return _write_json(
        directory / "cio_inputs.json",
        {"candidates": candidates, "context": context},
    )


def save_performance_report(report: Any, directory: Path) -> Path:
    if is_dataclass(report):
        payload = asdict(report)
    elif isinstance(report, dict):
        payload = report
    else:
        raise TypeError("report must be a dataclass or dict")
    return _write_json(directory / "performance_report.json", payload)


def save_intraday_flags(directory: Path, flags: dict[str, str]) -> Path:
    return _write_json(directory / "intraday_flags.json", flags)