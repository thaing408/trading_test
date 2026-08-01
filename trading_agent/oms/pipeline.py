"""OMS-aware consume pipeline: pretrade → submit → state → manage."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from trading_agent.export import mac_execute as mx
from trading_agent.oms.audit import append_audit
from trading_agent.oms.exits import manage_enabled, manage_open_lots
from trading_agent.oms.kill_switch import is_killed, kill_switch_status
from trading_agent.oms.multileg import attach_package_to_order, try_sequential_submit
from trading_agent.oms.pretrade import PretradeConfig, evaluate_pretrade, pretrade_snapshot
from trading_agent.oms.protect import mark_lot_open_from_submit
from trading_agent.oms.state import LotStatus, OpenLot, OmsStore


def _lot_from_order(order: mx.ReadyOrder, place_path: str) -> OpenLot:
    return OpenLot(
        lot_id=order.order_id,
        fingerprint=order.order_id,
        symbol=order.symbol,
        instrument=order.instrument,
        strategy=order.strategy,
        setup_id=order.setup_id,
        side=order.side,
        quantity=int(order.quantity or 0),
        entry=float(order.entry or 0),
        stop=float(order.stop or 0),
        target=float(order.target or 0),
        max_risk_dollars=float(order.max_risk_dollars or 0),
        status=LotStatus.PENDING.value,
        strike_prices=list(order.strike_prices or []),
        expiration=order.expiration or "",
        place_path=place_path,
        source_book=order.source_book,
        notes=order.notes,
        expected_entry=float(order.entry or 0),
    )


def run_oms_consume(
    *,
    paths: Optional[Sequence[Path]] = None,
    live: bool = False,
    mark_processed: bool = True,
    manage: Optional[bool] = None,
    store: Optional[OmsStore] = None,
) -> Dict[str, Any]:
    """Full consume with OMS gates, audit, and optional manage loop."""
    oms = store or OmsStore()
    day_key = datetime.now(mx.PT).date().isoformat()
    oms.ensure_day(day_key)

    cfg = PretradeConfig.from_env()
    snapshot = pretrade_snapshot(oms, cfg)
    append_audit("consume_start", payload={"live": live, "pretrade": snapshot})

    if is_killed():
        append_audit("consume_blocked_kill_switch", payload=kill_switch_status())
        # Still run manage/flatten if requested
        manage_results: List[Dict[str, Any]] = []
        if manage if manage is not None else manage_enabled():
            manage_results = manage_open_lots(
                oms,
                live=live,
                call_mcp=lambda t, p: mx.call_schwab_mcp(t, p),
            )
        oms.save()
        return {
            "blocked": True,
            "reason": "kill_switch",
            "kill_switch": kill_switch_status(),
            "pretrade": snapshot,
            "orders": [],
            "manage": manage_results,
            "live": live,
            "checklist": mx.format_checklist([], live=live),
            "books": [],
            "ready_orders_path": "",
            "submitted_ids": [],
        }

    candidates = list(paths) if paths else mx.book_candidates()
    books: List[Dict[str, Any]] = []
    found_paths: List[str] = []
    for p in candidates:
        book = mx.load_book(Path(p))
        if book:
            books.append(book)
            found_paths.append(str(p))

    processed = oms.processed_ids() | mx.load_processed_ids(
        mx.default_state_dir() / "auto_trade_processed.json"
    )
    orders = mx.build_ready_orders(books, processed=processed)

    submitted_ids: List[str] = []
    submit_count = 0

    for i, order in enumerate(orders):
        if order.status == "skipped":
            append_audit(
                "order_skipped",
                payload={"order_id": order.order_id, "symbol": order.symbol, "reason": order.skip_reason},
            )
            continue

        place_path = mx.classify_place_path(order)
        ok, reason = evaluate_pretrade(
            order,
            oms,
            config=cfg,
            submitted_this_run=submit_count,
        )
        if not ok:
            order.status = "skipped"
            order.skip_reason = reason
            orders[i] = order
            append_audit(
                "order_pretrade_block",
                payload={"order_id": order.order_id, "symbol": order.symbol, "reason": reason},
            )
            continue

        # Multi-leg / credit: build package; optional sequential
        if place_path in ("multi_leg_ready", "credit_ready"):
            if place_path == "multi_leg_ready" or (
                place_path == "credit_ready" and len(order.strike_prices or []) >= 2
            ):
                if live:
                    orders[i] = try_sequential_submit(
                        order,
                        live=live,
                        call_mcp=lambda t, p: mx.call_schwab_mcp(t, p),
                    )
                else:
                    orders[i] = attach_package_to_order(order)
                    orders[i].status = "dry_run"
                    orders[i].broker_response = {
                        **(orders[i].broker_response or {}),
                        "mode": "dry_run",
                        "place_path": place_path,
                        "message": "Multi-leg/credit package ready; live sequential off by default",
                    }
            else:
                # single-leg credit (e.g. short put naked) — never auto
                orders[i] = mx.submit_order(order, live=False)
                orders[i].status = "ready"
                orders[i].broker_response = {
                    "mode": "ready_only",
                    "place_path": place_path,
                    "message": "Credit/short-premium single-leg not auto-submitted",
                }
        else:
            orders[i] = mx.submit_order(order, live=live)

        order = orders[i]
        append_audit(
            "order_submit_result",
            payload={
                "order_id": order.order_id,
                "symbol": order.symbol,
                "status": order.status,
                "place_path": place_path,
                "live": live,
                "broker": order.broker_response,
            },
        )

        if order.status == "submitted":
            submit_count += 1
            submitted_ids.append(order.order_id)
            lot = _lot_from_order(order, place_path)
            lot.status = LotStatus.SUBMITTED.value
            lot.submitted_at = datetime.now(timezone.utc).isoformat()
            mark_lot_open_from_submit(
                oms,
                lot,
                broker_response=order.broker_response,
                fill_entry=float(order.entry or 0),
            )
            if mark_processed:
                oms.mark_processed(order.order_id)
        elif order.status in ("ready", "dry_run") and place_path in (
            "multi_leg_ready",
            "credit_ready",
        ):
            # Ensure package present for TOS
            orders[i] = attach_package_to_order(order)

    if mark_processed and submitted_ids:
        # keep legacy file in sync for older tools
        legacy = mx.default_state_dir() / "auto_trade_processed.json"
        legacy_ids = mx.load_processed_ids(legacy) | set(submitted_ids)
        mx.save_processed_ids(legacy, legacy_ids)

    manage_results = []
    if manage if manage is not None else manage_enabled():
        manage_results = manage_open_lots(
            oms,
            live=live,
            call_mcp=lambda t, p: mx.call_schwab_mcp(t, p),
        )

    oms.save()
    out_path = mx.write_ready_orders(orders, live=live)
    text = mx.format_checklist(orders, live=live)
    result = {
        "blocked": False,
        "books": found_paths,
        "orders": [o.to_dict() for o in orders],
        "ready_orders_path": str(out_path),
        "live": live,
        "checklist": text,
        "submitted_ids": submitted_ids,
        "pretrade": pretrade_snapshot(oms, cfg),
        "manage": manage_results,
        "oms_state": str(oms.state_path),
        "open_lots": [lot.to_dict() for lot in oms.open_lots()],
    }
    append_audit(
        "consume_end",
        payload={
            "submitted": submitted_ids,
            "order_count": len(orders),
            "open_lots": len(oms.open_lots()),
        },
    )
    return result
