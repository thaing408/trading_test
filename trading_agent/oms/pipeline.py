"""OMS-aware consume pipeline: pretrade → submit → state → manage."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from trading_agent.export import mac_execute as mx
from trading_agent.oms.audit import append_audit
from trading_agent.oms.exits import manage_enabled, manage_open_lots
from trading_agent.oms.kill_switch import is_killed, kill_switch_status
from trading_agent.oms.lifecycle import (
    extract_legs_from_broker_response,
    register_submitted_lot,
)
from trading_agent.oms.multileg import (
    attach_package_to_order,
    multileg_live_allowed,
    try_sequential_submit,
)
from trading_agent.oms.broker import (
    fetch_account_balances,
    parse_tradable_cash,
    quote_debit_premium,
)
from trading_agent.oms.pretrade import (
    PretradeConfig,
    estimate_order_cash_required,
    evaluate_pretrade,
    pretrade_snapshot,
)
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
    mcp = lambda t, p: mx.call_schwab_mcp(t, p)  # noqa: E731 — local alias

    # Account cash / BP — LIVE always fetches; dry-run only when require_account_cash
    account_resp: Dict[str, Any] = {}
    cash_info: Dict[str, Any] = {"fetched": False, "live": bool(live)}
    remaining_cash: Optional[float] = None
    if live or cfg.require_account_cash:
        account_resp = fetch_account_balances(mcp)
        if account_resp.get("error"):
            cash_info = {
                "fetched": False,
                "live": bool(live),
                "error": account_resp.get("error"),
                "message": account_resp.get("message") or account_resp.get("stderr"),
            }
        else:
            raw_cash = parse_tradable_cash(account_resp, prefer=cfg.cash_metric)
            reserve = max(0.0, float(cfg.min_cash_reserve or 0.0))
            bal = account_resp.get("balances") or {}
            cash_info = {
                "fetched": True,
                "live": bool(live),
                "metric": cfg.cash_metric,
                "cash_available": bal.get("cash_available"),
                "buying_power": bal.get("buying_power"),
                "cash_balance": bal.get("cash_balance"),
                "total_value": bal.get("total_value"),
                "raw_tradable": raw_cash,
                "reserve": reserve,
                "tradable_after_reserve": (
                    None if raw_cash is None else max(0.0, float(raw_cash) - reserve)
                ),
            }
            if raw_cash is not None:
                remaining_cash = max(0.0, float(raw_cash) - reserve)

    snapshot = pretrade_snapshot(oms, cfg, account_cash=cash_info)
    append_audit(
        "consume_start",
        payload={"live": live, "pretrade": snapshot, "account_cash": cash_info},
    )

    # P2.3 — block LIVE place if Schwab OAuth is fully expired / missing
    schwab_block = ""
    if live:
        try:
            from trading_agent.ops.schwab_health import (
                schwab_live_blocked_reason,
                schwab_oauth_status,
            )

            schwab_block = schwab_live_blocked_reason()
            snapshot["schwab_oauth"] = schwab_oauth_status()
        except Exception as exc:  # noqa: BLE001
            snapshot["schwab_oauth_error"] = str(exc)

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

    book_summary = mx.summarize_books(books)
    append_audit("books_loaded", payload={"books": book_summary})

    processed = oms.processed_ids() | mx.load_processed_ids(
        mx.default_state_dir() / "auto_trade_processed.json"
    )
    orders = mx.build_ready_orders(books, processed=processed)

    submitted_ids: List[str] = []
    processed_now: List[str] = []  # submitted + terminal fails/skips → no poll retry
    submit_count = 0
    # If LIVE but Schwab OAuth dead, force dry-run place path (still build ready_orders)
    effective_live = bool(live) and not schwab_block

    for i, order in enumerate(orders):
        if order.status == "skipped":
            append_audit(
                "order_skipped",
                payload={"order_id": order.order_id, "symbol": order.symbol, "reason": order.skip_reason},
            )
            continue

        place_path = mx.classify_place_path(order)
        process_detail: Dict[str, Any] = {}

        # Cash affordability (LIVE or when account balances loaded)
        premium_est: Optional[float] = None
        cash_need: Optional[float] = None
        enforce_cash = bool(live) or remaining_cash is not None
        if enforce_cash:
            if place_path == "single_leg_debit":
                ok_q, _reason_q, meta = mx.option_contract_precheck(order)
                if ok_q and meta.get("occ_symbol"):
                    premium_est = quote_debit_premium(
                        mcp,
                        occ=str(meta["occ_symbol"]),
                        quantity=max(1, int(order.quantity or 1)),
                        buffer=float(cfg.cash_buffer or 1.05),
                    )
                    # Downsize qty if cash only covers 1 contract of multi-lot
                    if (
                        premium_est is not None
                        and remaining_cash is not None
                        and int(order.quantity or 1) > 1
                    ):
                        one_est = quote_debit_premium(
                            mcp,
                            occ=str(meta["occ_symbol"]),
                            quantity=1,
                            buffer=float(cfg.cash_buffer or 1.05),
                        )
                        if (
                            one_est is not None
                            and premium_est > remaining_cash
                            and one_est <= remaining_cash
                        ):
                            order.quantity = 1
                            premium_est = one_est
                            order.notes = (
                                (order.notes or "")
                                + f"; qty_cut_to_1 cash={remaining_cash:.0f}"
                            )[:240]
                cash_need = estimate_order_cash_required(
                    order,
                    premium_dollars=premium_est,
                    buffer=float(cfg.cash_buffer or 1.05),
                )
            else:
                cash_need = estimate_order_cash_required(
                    order, buffer=float(cfg.cash_buffer or 1.05)
                )

        # LIVE without balances → fail closed via account_cash_unavailable
        bp_for_gate = remaining_cash if enforce_cash else None
        cash_req_for_gate = cash_need if enforce_cash else None
        # Temporarily force require_account_cash only on LIVE
        gate_cfg = cfg
        if not live and remaining_cash is None:
            # dry-run unit paths without MCP: skip cash gate
            from dataclasses import replace

            gate_cfg = replace(cfg, require_account_cash=False)

        ok, reason = evaluate_pretrade(
            order,
            oms,
            config=gate_cfg,
            submitted_this_run=submit_count,
            buying_power=bp_for_gate,
            cash_required=cash_req_for_gate,
            process_detail=process_detail,
        )
        if not ok:
            order.status = "skipped"
            order.skip_reason = reason
            order.broker_response = {
                "mode": "pretrade_cash",
                "cash_required": cash_need,
                "remaining_cash": remaining_cash,
                "premium_est": premium_est,
                "account_cash": cash_info,
            }
            orders[i] = order
            append_audit(
                "order_pretrade_block",
                payload={
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "reason": reason,
                    "cash_required": cash_need,
                    "remaining_cash": remaining_cash,
                    "premium_est": premium_est,
                    "process_gate": process_detail or None,
                },
            )
            continue

        if schwab_block and live:
            order.status = "skipped"
            order.skip_reason = schwab_block
            order.broker_response = {
                "mode": "blocked",
                "message": schwab_block,
                "schwab": snapshot.get("schwab_oauth"),
            }
            orders[i] = order
            append_audit(
                "order_schwab_health_block",
                payload={"order_id": order.order_id, "symbol": order.symbol, "reason": schwab_block},
            )
            continue

        # Hard gate: no LIVE MARKET place before RTH (09:30 ET). Prep/ready_orders OK.
        # Do NOT mark_processed — retry after the open.
        rth_block = ""
        if effective_live:
            rth_block = mx.live_entry_blocked_reason()
        if rth_block:
            order.status = "skipped"
            order.skip_reason = rth_block
            order.broker_response = {
                "mode": "rth_gate",
                "message": (
                    "LIVE place blocked until regular session open (09:30 ET). "
                    "ready_orders still written; will retry after open."
                ),
                "place_path": place_path,
            }
            orders[i] = order
            append_audit(
                "order_rth_gate",
                payload={
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "reason": rth_block,
                    "live": True,
                },
            )
            continue

        # Explicit affordability (debit premium / credit margin) before any LIVE place.
        # Complements evaluate_pretrade cash gate; covers credit/SELL_TO_OPEN paths.
        if effective_live:
            from trading_agent.oms.affordability import check_open_affordability

            cash_snapshot = dict(cash_info or {})
            if remaining_cash is not None:
                cash_snapshot["remaining_after_submits"] = remaining_cash
            afford = check_open_affordability(
                order,
                place_path=place_path,
                account_cash=cash_snapshot,
                premium_est=premium_est,
                buffer=float(cfg.cash_buffer or 1.05),
                require_balances=True,
            )
            if not afford.ok:
                order.status = "skipped"
                order.skip_reason = afford.reason
                order.broker_response = {
                    "mode": "affordability",
                    "affordability": afford.as_dict(),
                    "place_path": place_path,
                    "message": (
                        "LIVE place blocked — account balance/BP cannot fund this order"
                    ),
                }
                orders[i] = order
                append_audit(
                    "order_affordability_block",
                    payload={
                        "order_id": order.order_id,
                        "symbol": order.symbol,
                        "reason": afford.reason,
                        "need": afford.need,
                        "have": afford.have,
                        "kind": afford.kind,
                        "place_path": place_path,
                    },
                )
                continue

        # Multi-leg / credit: package always; LIVE sequential when MULTILEG_LIVE allowed
        if place_path in ("multi_leg_ready", "credit_ready"):
            if place_path == "multi_leg_ready" or (
                place_path == "credit_ready" and len(order.strike_prices or []) >= 2
            ):
                if effective_live and multileg_live_allowed():
                    orders[i] = try_sequential_submit(
                        order,
                        live=True,
                        call_mcp=lambda t, p: mx.call_schwab_mcp(t, p),
                    )
                else:
                    orders[i] = attach_package_to_order(order)
                    orders[i].status = "dry_run" if not effective_live else "ready"
                    orders[i].broker_response = {
                        **(orders[i].broker_response or {}),
                        "mode": "dry_run" if not effective_live else "ready_only",
                        "place_path": place_path,
                        "message": (
                            "Multi-leg package ready; enable "
                            "TRADING_AGENT_MULTILEG_LIVE=1 for wing-first LIVE "
                            "(with one-leg reverse on failure)"
                        ),
                    }
            else:
                # single-leg credit naked — never auto
                orders[i] = mx.submit_order(order, live=False)
                orders[i].status = "ready"
                orders[i].broker_response = {
                    "mode": "ready_only",
                    "place_path": place_path,
                    "message": "Credit/short-premium single-leg not auto-submitted",
                }
        else:
            orders[i] = mx.submit_order(order, live=effective_live)

        order = orders[i]
        append_audit(
            "order_submit_result",
            payload={
                "order_id": order.order_id,
                "symbol": order.symbol,
                "status": order.status,
                "place_path": place_path,
                "live": effective_live,
                "broker": order.broker_response,
            },
        )

        if order.status == "submitted":
            from trading_agent.oms.lifecycle import broker_fill_confirmed

            lot = _lot_from_order(order, place_path)
            legs = extract_legs_from_broker_response(order.broker_response or {})
            registered = register_submitted_lot(
                oms,
                lot,
                broker_response=order.broker_response,
                fill_entry=float(order.entry or 0),
                legs=legs or None,
            )
            # Only count true fills / working orders toward open-lot slots
            if broker_fill_confirmed(order.broker_response or {}) and registered.status not in (
                "failed",
                "closed",
            ):
                submit_count += 1
                submitted_ids.append(order.order_id)
                # Store option entry premium for QQQ-style % exits + journal Fill:
                prem: Optional[float] = None
                spot: Optional[float] = None
                try:
                    from trading_agent.oms.broker import quote_last_price

                    occ = str(
                        (order.broker_response or {}).get("occ_symbol")
                        or registered.occ_symbol
                        or ""
                    )
                    spot = quote_last_price(mcp, order.symbol)
                    if occ and (registered.instrument or "").lower() in ("options", "option"):
                        prem = quote_last_price(mcp, occ)
                        if prem is not None and 0 < prem < 50:
                            registered.fill_entry = float(prem)
                            meta = dict(registered.broker_meta or {})
                            meta["option_entry_premium"] = float(prem)
                            registered.broker_meta = meta
                            oms.upsert_lot(registered)
                            br = dict(order.broker_response or {})
                            br["option_entry_premium"] = float(prem)
                            order.broker_response = br
                            orders[i] = order
                except Exception as exc:  # noqa: BLE001
                    append_audit(
                        "option_premium_capture_error",
                        payload={"order_id": order.order_id, "error": str(exc)},
                    )
                # Debit local cash ledger so next orders see reduced BP
                if remaining_cash is not None and cash_need is not None:
                    remaining_cash = max(0.0, float(remaining_cash) - float(cash_need))
                    cash_info["remaining_after_submits"] = remaining_cash
                if mark_processed:
                    oms.mark_processed(order.order_id)
                    processed_now.append(order.order_id)
                if effective_live:
                    try:
                        from trading_agent.ops.journal_notify import notify_order_activity

                        notify_order_activity(
                            order,
                            live=True,
                            fill_price=prem,
                            spot_price=spot,
                        )
                    except Exception as exc:  # noqa: BLE001 — fail-open
                        append_audit(
                            "journal_notify_error",
                            payload={"order_id": order.order_id, "error": str(exc)},
                        )
            else:
                if order.status == "submitted":
                    order.status = "failed"
                    orders[i] = order
                if mark_processed:
                    oms.mark_processed(order.order_id)
                    processed_now.append(order.order_id)
                if effective_live:
                    try:
                        from trading_agent.ops.journal_notify import notify_order_activity

                        notify_order_activity(orders[i], live=True)
                    except Exception as exc:  # noqa: BLE001
                        append_audit(
                            "journal_notify_error",
                            payload={"order_id": order.order_id, "error": str(exc)},
                        )
        elif order.status == "failed":
            # Terminal place failures must not retry every poll (was Discord spam).
            if mark_processed:
                oms.mark_processed(order.order_id)
                processed_now.append(order.order_id)
            if effective_live:
                try:
                    from trading_agent.ops.journal_notify import notify_order_activity

                    notify_order_activity(order, live=True)
                except Exception as exc:  # noqa: BLE001
                    append_audit(
                        "journal_notify_error",
                        payload={"order_id": order.order_id, "error": str(exc)},
                    )
        elif order.status == "skipped" and order.skip_reason in (
            "occ_not_listed",
            "broker_reject_terminal",
        ):
            if mark_processed:
                oms.mark_processed(order.order_id)
                processed_now.append(order.order_id)
        elif order.status in ("ready", "dry_run") and place_path in (
            "multi_leg_ready",
            "credit_ready",
        ):
            orders[i] = attach_package_to_order(order)

    if mark_processed and processed_now:
        # keep legacy file in sync for older tools (includes terminal fails)
        legacy = mx.default_state_dir() / "auto_trade_processed.json"
        legacy_ids = mx.load_processed_ids(legacy) | set(processed_now)
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
    text = mx.format_checklist(orders, live=live, book_summary=book_summary)
    if schwab_block:
        text = f"SCHWAB_HEALTH_BLOCK={schwab_block}\n" + text
    result = {
        "blocked": False,
        "books": found_paths,
        "book_summary": book_summary,
        "schwab_block": schwab_block or None,
        "orders": [o.to_dict() for o in orders],
        "ready_orders_path": str(out_path),
        "live": live,
        "effective_live": effective_live,
        "checklist": text,
        "submitted_ids": submitted_ids,
        "pretrade": pretrade_snapshot(oms, cfg, account_cash=cash_info),
        "account_cash": cash_info,
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
