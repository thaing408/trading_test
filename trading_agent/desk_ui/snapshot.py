"""Assemble DeskSnapshot from local host files."""

from __future__ import annotations

import socket
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from trading_agent.desk_ui.config import detect_host_role
from trading_agent.desk_ui.market_context import MarketContext, build_market_context
from trading_agent.desk_ui.models import (
    DeskSnapshot,
    ExportHealth,
    ManageView,
    PositionsView,
)
from trading_agent.desk_ui.phase import PhaseStatus
from trading_agent.desk_ui.readers.auto_trade import load_auto_trade_book
from trading_agent.desk_ui.readers.export_health import compute_export_health
from trading_agent.desk_ui.readers.intelligence import load_intelligence
from trading_agent.desk_ui.readers.manage import load_manage_view
from trading_agent.desk_ui.readers.oms_view import load_kill_switch, load_oms_lots
from trading_agent.desk_ui.readers.positions import load_positions_view
from trading_agent.desk_ui.readers.process_cards import load_process_cards
from trading_agent.desk_ui.readers.scanned_list import load_scanned
from trading_agent.desk_ui.readers.schedule_status import resolve_phase
from trading_agent.desk_ui.readers.session_plan import load_plan_context, merge_rejections
from trading_agent.desk_ui.json_io import read_json_file
from trading_agent.desk_ui.paths import state_root, sync_dir, ui_sidecar_dir


def assemble_snapshot(
    *,
    now: datetime | None = None,
    trading_date: date | None = None,
    state: Path | None = None,
    positions_path: str | None = None,
    load_positions_fn: Any = None,
    platform: str | None = None,
    env: dict[str, str] | None = None,
) -> DeskSnapshot:
    """Build a full desk snapshot for this host (or fixture ``state`` root)."""
    parse_failures = 0
    panel_errors: dict[str, str] = {}

    td, schedule, phase = resolve_phase(now, trading_date=trading_date)
    td_s = td.isoformat()

    book_res = load_auto_trade_book(trading_date=td_s, state=state)
    if book_res.error and book_res.error != "missing":
        parse_failures += 1
        panel_errors["book"] = book_res.error
    book = book_res.data or {}
    if not book:
        stay_in_cash = True
        cash_reason = "book missing"
        book_role = ""
        entries: list[dict[str, Any]] = []
        watchlist: list[str] = []
        broker_boundary = ""
        environment_score = None
        regime = ""
    else:
        stay_in_cash = bool(book.get("stay_in_cash", False))
        cash_reason = str(book.get("cash_reason") or book.get("cash_recommendation_reason") or "")
        book_role = str(book.get("role") or "")
        entries = list(book.get("entries") or [])
        watchlist = [str(s).upper() for s in (book.get("watchlist") or book.get("scan_symbols") or [])]
        broker_boundary = str(book.get("broker_boundary") or "")
        try:
            environment_score = (
                float(book["environment_score"])
                if book.get("environment_score") is not None
                else (
                    float(book["market_environment_score"])
                    if book.get("market_environment_score") is not None
                    else None
                )
            )
        except (TypeError, ValueError):
            environment_score = None
        regime = str(book.get("regime") or book.get("market_regime") or "")

    scanned_res = load_scanned(trading_date=td_s, state=state)
    if scanned_res.error and scanned_res.error not in ("missing",):
        parse_failures += 1
        panel_errors["scanned"] = scanned_res.error
    scanned = scanned_res.data or {}
    play_symbols = [
        str(s).upper()
        for s in (
            scanned.get("play_symbols")
            or scanned.get("play")
            or book.get("play_symbols")
            or []
        )
    ]
    if not watchlist:
        watchlist = [str(s).upper() for s in (scanned.get("watchlist") or scanned.get("symbols") or [])]

    plan_res = load_plan_context(td, state=state)
    if plan_res.error and plan_res.error != "missing":
        parse_failures += 1
        panel_errors["plan"] = plan_res.error
    plan = plan_res.data or {}
    # Prefer longer cash reason from plan
    plan_cash = str(plan.get("cash_recommendation_reason") or "")
    if plan_cash and (not cash_reason or len(plan_cash) > len(cash_reason)):
        cash_reason = plan_cash
    if plan.get("stay_in_cash") and not book:
        stay_in_cash = True
    if environment_score is None and plan.get("market_environment_score") is not None:
        try:
            environment_score = float(plan["market_environment_score"])
        except (TypeError, ValueError):
            pass
    if not regime:
        regime = str(plan.get("market_regime") or plan.get("overall_market_bias") or "")

    intel_res = load_intelligence(td, state=state)
    if intel_res.error and intel_res.error not in ("missing",):
        parse_failures += 1
        panel_errors["intelligence"] = intel_res.error
    intelligence = intel_res.data or {}

    # Prefer short regime code on snapshot.regime; full text lives in market.raw_bias
    regime_code = str(plan.get("market_regime") or "").strip()
    if regime_code and len(regime_code) <= 40:
        regime = regime_code
    elif intelligence.get("outlook"):
        regime = str(intelligence.get("outlook") or "")
    # else keep existing regime (may still be long free text — market table will parse)

    market: MarketContext = build_market_context(
        environment_score=environment_score,
        regime=regime,
        plan=plan,
        book=book,
        intelligence=intelligence,
    )
    if market.environment_score is not None:
        environment_score = market.environment_score
    if market.bias_short and (not regime or len(regime) > 48):
        regime = market.bias_short

    rejections = merge_rejections(plan, book)

    export_health = compute_export_health(
        td,
        book,
        now=now,
        schedule=schedule,
        state=state,
        plan_missing=bool(plan_res.error),
    )

    manage = load_manage_view(
        td,
        now=now,
        in_intraday_window=phase.in_intraday_window,
        log_dir=(Path(state) / "logs" / "manage") if state else None,
    )

    positions = load_positions_view(
        path=positions_path,
        load_positions_fn=load_positions_fn,
    )

    oms_root = (Path(state) / "oms") if state else None
    oms_lots = load_oms_lots(oms_root=oms_root)
    kill_switch = load_kill_switch()

    cards, cards_err = load_process_cards(td, state=state)
    if cards_err and cards_err not in ("missing",):
        parse_failures += 1
        panel_errors["process"] = cards_err

    gap_summary = _gap_book_summary(state)

    op_flags, acks = _load_ui_sidecars(td, state=state)

    host_role = detect_host_role(
        platform=platform,
        env=env,
        oms_root=oms_root,
        state_root=Path(state) if state else state_root(),
    )

    generated = datetime.now(timezone.utc).isoformat()

    return DeskSnapshot(
        trading_date=td_s,
        host=socket.gethostname(),
        host_role=host_role,
        book_role=book_role,
        phase=phase,
        stay_in_cash=stay_in_cash,
        cash_reason=cash_reason,
        environment_score=environment_score,
        regime=regime,
        market=market,
        book_raw=book,
        scanned_raw=scanned,
        entries=entries if isinstance(entries, list) else [],
        watchlist=watchlist,
        play_symbols=play_symbols,
        rejections=rejections,
        export_health=export_health,
        manage=manage,
        positions=positions,
        oms_lots=oms_lots,
        kill_switch=kill_switch,
        process_cards=cards,
        gap_book_summary=gap_summary,
        operator_flags=op_flags,
        acknowledgements=acks,
        broker_boundary=broker_boundary,
        generated_at=generated,
        platform=platform or sys.platform,
        parse_failures=parse_failures,
        panel_errors=panel_errors,
    )


def _gap_book_summary(state: Path | None) -> dict[str, Any] | None:
    if state is not None:
        path = Path(state) / "sync" / "gap_screener_book.json"
    else:
        path = sync_dir() / "gap_screener_book.json"
    data, err = read_json_file(path)
    if err or not isinstance(data, dict):
        return None
    return {
        "path": str(path),
        "entry_count": data.get("entry_count"),
        "stay_in_cash": data.get("stay_in_cash"),
        "trading_date": data.get("trading_date"),
        "symbol_count": len(data.get("entries") or data.get("symbols") or []),
    }


def _load_ui_sidecars(
    trading_date: date,
    *,
    state: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if state is not None:
        ui = Path(state) / "ui"
    else:
        ui = ui_sidecar_dir()
    flags_path = ui / "operator_flags.json"
    acks_path = ui / f"acks_{trading_date.isoformat()}.json"
    flags, _ = read_json_file(flags_path)
    acks, _ = read_json_file(acks_path)
    return (
        flags if isinstance(flags, dict) else {},
        acks if isinstance(acks, dict) else {},
    )


# Re-export types for convenience
__all__ = [
    "DeskSnapshot",
    "ExportHealth",
    "ManageView",
    "PhaseStatus",
    "PositionsView",
    "assemble_snapshot",
]
