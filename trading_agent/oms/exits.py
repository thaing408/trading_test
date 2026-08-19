"""Exit / manage loop: close open lots via Schwab MCP when rules fire."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from trading_agent.journal.trades import JournalTrade, append_journal_trade
from trading_agent.oms.audit import append_audit
from trading_agent.oms.broker import (
    close_instruction_for_open_leg,
    flatten_symbols,
    order_submitted_ok,
    place_equity,
    place_option,
)
from trading_agent.oms.kill_switch import should_flatten
from trading_agent.oms.protect import should_exit_lot
from trading_agent.oms.state import LotStatus, OpenLot, OmsStore


McpCaller = Callable[[str, Dict[str, Any]], Dict[str, Any]]


def _close_instruction(lot: OpenLot) -> str:
    instr = (lot.instrument or "").lower()
    if instr in ("options", "option"):
        path = (lot.place_path or "").lower()
        strat = (lot.strategy or "").lower()
        if "credit" in path or "credit" in strat or "short" in (lot.side or "").lower():
            if "debit" not in strat:
                return "BUY_TO_CLOSE"
        return "SELL_TO_CLOSE"
    return "SELL"


def _legs_for_lot(lot: OpenLot) -> List[Dict[str, Any]]:
    legs = (lot.broker_meta or {}).get("legs") or []
    if isinstance(legs, list) and legs:
        return [leg for leg in legs if isinstance(leg, dict)]
    pkg = (lot.broker_meta or {}).get("multileg_package") or {}
    if isinstance(pkg, dict):
        return [leg for leg in (pkg.get("legs") or []) if isinstance(leg, dict)]
    # also check nested place responses
    for item in (lot.broker_meta or {}).get("responses") or []:
        if isinstance(item, dict) and isinstance(item.get("leg"), dict):
            legs.append(item["leg"])
    return [leg for leg in legs if isinstance(leg, dict)]


def _account_cash_snapshot(call_mcp: McpCaller) -> Dict[str, Any]:
    try:
        from trading_agent.oms.broker import fetch_account_balances, parse_tradable_cash
        from trading_agent.oms.pretrade import PretradeConfig

        cfg = PretradeConfig.from_env()
        resp = fetch_account_balances(call_mcp)
        if resp.get("error"):
            return {
                "fetched": False,
                "error": resp.get("error"),
                "message": resp.get("message") or resp.get("stderr"),
            }
        raw = parse_tradable_cash(resp, prefer=cfg.cash_metric)
        reserve = max(0.0, float(cfg.min_cash_reserve or 0.0))
        bal = resp.get("balances") or {}
        return {
            "fetched": True,
            "metric": cfg.cash_metric,
            "cash_available": bal.get("cash_available"),
            "buying_power": bal.get("buying_power"),
            "cash_balance": bal.get("cash_balance"),
            "raw_tradable": raw,
            "reserve": reserve,
            "tradable_after_reserve": (
                None if raw is None else max(0.0, float(raw) - reserve)
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {"fetched": False, "error": str(exc)}


def submit_close(
    lot: OpenLot,
    *,
    live: bool,
    call_mcp: McpCaller,
    reason: str,
) -> Dict[str, Any]:
    """Submit close for a lot. Multi-leg closes each OCC with inverse instruction."""
    qty = max(1, int(lot.quantity or 1))
    instrument = (lot.instrument or "").lower()
    legs = _legs_for_lot(lot)

    # LIVE: verify account can fund BUY_TO_CLOSE (short buyback) before place_order.
    if live:
        from trading_agent.oms.affordability import check_close_affordability
        from trading_agent.oms.broker import quote_last_price

        primary_instr = _close_instruction(lot)
        if legs:
            # If any leg needs BUY_TO_CLOSE, gate on that
            for leg in legs:
                open_i = str(leg.get("instruction") or "BUY_TO_OPEN")
                from trading_agent.oms.broker import close_instruction_for_open_leg

                if close_instruction_for_open_leg(open_i) == "BUY_TO_CLOSE":
                    primary_instr = "BUY_TO_CLOSE"
                    break

        cash = _account_cash_snapshot(call_mcp)
        buyback = None
        if primary_instr == "BUY_TO_CLOSE":
            occ = (lot.occ_symbol or "").strip()
            if occ:
                try:
                    px = quote_last_price(call_mcp, occ)
                    if px is not None and 0 < float(px) < 50:
                        buyback = float(px) * 100.0 * qty * 1.15
                except Exception:
                    buyback = None
        afford = check_close_affordability(
            lot,
            instruction=primary_instr,
            account_cash=cash,
            buyback_premium_est=buyback,
            require_balances=True,
        )
        if not afford.ok:
            append_audit(
                "close_affordability_block",
                payload={
                    "lot_id": lot.lot_id,
                    "symbol": lot.symbol,
                    "instruction": primary_instr,
                    "reason": afford.reason,
                    "need": afford.need,
                    "have": afford.have,
                    "exit_reason": reason,
                },
            )
            return {
                "error": afford.reason,
                "mode": "affordability_block",
                "status": "blocked",
                "dry_run": False,
                "reason": reason,
                "affordability": afford.as_dict(),
                "message": (
                    "LIVE close blocked — account balance/BP cannot fund this exit"
                ),
            }

    if instrument in ("options", "option") and len(legs) >= 2:
        responses = []
        all_ok = True
        for leg in legs:
            occ = str(leg.get("occ_symbol") or "")
            if not occ:
                continue
            open_i = str(leg.get("instruction") or "BUY_TO_OPEN")
            close_i = close_instruction_for_open_leg(open_i)
            lqty = int(leg.get("quantity") or qty)
            resp = place_option(
                call_mcp,
                occ=occ,
                quantity=lqty,
                instruction=close_i,
                live=live,
            )
            responses.append({"occ": occ, "instruction": close_i, "response": resp})
            if not order_submitted_ok(resp):
                all_ok = False
        return {
            "mode": "multileg_close",
            "status": "submitted" if all_ok and live else ("dry_run" if not live else "partial"),
            "dry_run": not live,
            "reason": reason,
            "responses": responses,
            "error": None if all_ok else "partial_multileg_close",
        }

    if instrument in ("options", "option"):
        symbol = (lot.occ_symbol or "").strip()
        if not symbol:
            return {
                "error": "missing_occ",
                "mode": "ready_only",
                "message": "No OCC on lot — close multi-leg in TOS",
                "reason": reason,
            }
        return place_option(
            call_mcp,
            occ=symbol,
            quantity=qty,
            instruction=_close_instruction(lot),
            live=live,
        )

    return place_equity(
        call_mcp,
        symbol=lot.symbol,
        quantity=qty,
        instruction="SELL",
        live=live,
    )


def close_lot(
    store: OmsStore,
    lot: OpenLot,
    *,
    live: bool,
    call_mcp: McpCaller,
    reason: str,
    exit_price: float = 0.0,
    journal: bool = True,
) -> OpenLot:
    lot.status = LotStatus.EXITING.value
    store.upsert_lot(lot)
    resp = submit_close(lot, live=live, call_mcp=call_mcp, reason=reason)
    lot.broker_meta = {**(lot.broker_meta or {}), "close": resp}

    ok = not resp.get("error")
    status = str(resp.get("status") or "").lower()
    if live and ok and (status == "submitted" or resp.get("dry_run") is False):
        lot.status = LotStatus.CLOSED.value
        lot.closed_at = datetime.now(timezone.utc).isoformat()
        lot.exit_reason = reason
        lot.exit_price = float(exit_price or lot.fill_entry or lot.entry or 0)
        # P/L: equity shares = (exit-entry)*qty; option premium = (exit-entry)*qty*100
        # when both prices look like option premiums (< $50).
        entry = float(lot.fill_entry or lot.entry or 0)
        exit_px = float(lot.exit_price or 0)
        pnl = 0.0
        instr = (lot.instrument or "").lower()
        if entry and exit_px:
            if instr in ("equity", "underlying", "etf", "stock"):
                pnl = (exit_px - entry) * int(lot.quantity or 0)
            elif instr in ("options", "option") and entry < 50 and exit_px < 50:
                pnl = (exit_px - entry) * int(lot.quantity or 1) * 100.0
        store.add_realized_pnl(pnl)
        try:
            trips = store.record_round_trip(lot.symbol)
        except Exception:
            trips = 0
        if journal:
            _journal_close(lot, pnl=pnl)
        append_audit(
            "lot_closed",
            payload={
                "lot_id": lot.lot_id,
                "symbol": lot.symbol,
                "reason": reason,
                "pnl": pnl,
                "symbol_round_trips_today": trips,
            },
        )
        if live:
            try:
                from trading_agent.export import mac_execute as mx

                # Schwab #trading-journal path; IBKR paper uses discord.paper_activity instead
                if str(mx.broker_name() or "").lower() != "ibkr":
                    from trading_agent.ops.journal_notify import notify_exit_activity
                    from trading_agent.oms.broker import quote_last_price

                    opt_mark = float(exit_price) if exit_price and float(exit_price) < 50 else None
                    opt_entry = None
                    meta = lot.broker_meta or {}
                    for key in ("option_entry_premium", "entry_option_price"):
                        try:
                            v = float(meta.get(key) or 0)
                        except (TypeError, ValueError):
                            v = 0.0
                        if 0 < v < 50:
                            opt_entry = v
                            break
                    if opt_entry is None and lot.fill_entry and float(lot.fill_entry) < 50:
                        opt_entry = float(lot.fill_entry)

                    spot = None
                    try:
                        spot = quote_last_price(lambda t, p: mx.call_schwab_mcp(t, p), lot.symbol)
                    except Exception:
                        spot = None

                    close_oid = ""
                    close = (lot.broker_meta or {}).get("close") or {}
                    if isinstance(close, dict):
                        from trading_agent.ops.journal_notify import _schwab_order_id

                        close_oid = _schwab_order_id(close) or _schwab_order_id(
                            close.get("response") if isinstance(close.get("response"), dict) else close
                        )

                    notify_exit_activity(
                        lot,
                        reason=reason,
                        live=True,
                        pnl=pnl if pnl else None,
                        option_mark=opt_mark,
                        option_entry=opt_entry,
                        spot_price=spot,
                        order_id=close_oid,
                    )
            except Exception as exc:  # noqa: BLE001 — fail-open
                append_audit(
                    "journal_notify_error",
                    payload={"lot_id": lot.lot_id, "error": str(exc)},
                )
    elif not live:
        lot.status = LotStatus.EXITING.value
        lot.exit_reason = reason
        lot.broker_meta["close_mode"] = "dry_run"
        append_audit(
            "lot_close_dry_run",
            payload={"lot_id": lot.lot_id, "symbol": lot.symbol, "reason": reason},
        )
    else:
        lot.status = LotStatus.PROTECTED.value if lot.stop else LotStatus.OPEN.value
        append_audit(
            "lot_close_failed",
            payload={"lot_id": lot.lot_id, "symbol": lot.symbol, "resp": resp},
        )
    store.upsert_lot(lot)
    return lot


def _journal_close(lot: OpenLot, *, pnl: float) -> None:
    append_journal_trade(
        JournalTrade(
            symbol=lot.symbol,
            entry=float(lot.fill_entry or lot.entry or 0),
            exit=float(lot.exit_price or 0),
            profit_loss=pnl,
            strategy=lot.strategy,
            setup_id=lot.setup_id,
            direction=lot.side,
            stop_loss=float(lot.stop or 0),
            profit_target=float(lot.target or 0),
            exit_reason=lot.exit_reason,
            entry_time=lot.opened_at,
            exit_time=lot.closed_at,
            notes=f"oms lot={lot.lot_id} slip={lot.slippage:.4f} path={lot.place_path}",
            expected_entry=float(lot.expected_entry or lot.entry or 0),
            fill_entry=float(lot.fill_entry or 0),
            slippage=float(lot.slippage or 0),
            lot_id=lot.lot_id,
            place_path=lot.place_path,
        )
    )


def flatten_all_lots(
    store: OmsStore,
    *,
    live: bool,
    call_mcp: McpCaller,
    also_broker_account: bool = True,
) -> Dict[str, Any]:
    """Close every OMS open lot; optionally also flatten matching broker positions."""
    results = []
    for lot in list(store.open_lots()):
        close_lot(
            store,
            lot,
            live=live,
            call_mcp=call_mcp,
            reason="flatten_all",
        )
        results.append({"lot_id": lot.lot_id, "status": lot.status})
    broker = {}
    if also_broker_account:
        # Flatten OMS symbols + full account sweep when kill flatten is requested
        syms = list({lot.symbol for lot in store.all_lots() if lot.status != LotStatus.CLOSED.value})
        broker = flatten_symbols(call_mcp, live=live, symbols=syms or None)
    store.save()
    append_audit(
        "flatten_all",
        payload={"live": live, "lots": len(results), "broker_ok": broker.get("ok")},
    )
    return {"lots": results, "broker": broker}


def manage_open_lots(
    store: OmsStore,
    *,
    live: bool,
    call_mcp: McpCaller,
    marks: Optional[Dict[str, float]] = None,
    underlying_marks: Optional[Dict[str, float]] = None,
    reconcile_first: bool = True,
) -> List[Dict[str, Any]]:
    """Evaluate open lots for stop/target or flatten kill.

    When marks are not supplied (normal consumer path), fetch live Schwab
    underlying quotes + option marks from positions — same idea as QQQ scalp
    manage cycle, applied to every multi-method lot.
    """
    marks = dict(marks or {})
    underlying_marks = dict(underlying_marks or {})
    results: List[Dict[str, Any]] = []

    if reconcile_first and live:
        try:
            from trading_agent.oms.lifecycle import prune_ghost_lots_ibkr, reconcile_open_lots

            # Paper IBKR: drop ghost lots not in portfolio (fixes max_open_lots deadlock)
            try:
                prune_ghost_lots_ibkr(store)
            except Exception as prune_exc:  # noqa: BLE001
                append_audit("prune_exception", payload={"error": str(prune_exc)})
            reconcile_open_lots(store, call_mcp)
        except Exception as exc:
            append_audit("reconcile_exception", payload={"error": str(exc)})

    flatten = should_flatten()
    if flatten:
        flat = flatten_all_lots(store, live=live, call_mcp=call_mcp, also_broker_account=True)
        results.append({"action": "flatten_all", "detail": flat})
        return results

    open_lots = [
        lot
        for lot in list(store.open_lots())
        if lot.status
        in (
            LotStatus.OPEN.value,
            LotStatus.PROTECTED.value,
            LotStatus.SUBMITTED.value,
            LotStatus.EXITING.value,
        )
    ]

    # Auto-fetch live prices when caller did not supply marks (Mac consumer)
    pos_index: Dict[str, Any] = {}
    if live and open_lots and (not underlying_marks or not marks):
        try:
            from trading_agent.oms.broker import fetch_marks_for_lots, position_avg_price

            live_marks = fetch_marks_for_lots(call_mcp, open_lots)
            for k, v in (live_marks.get("underlying") or {}).items():
                underlying_marks.setdefault(str(k).upper(), float(v))
            for k, v in (live_marks.get("option") or {}).items():
                marks.setdefault(str(k), float(v))
            pos_index = live_marks.get("positions_index") or {}
            append_audit(
                "manage_marks_fetched",
                payload={
                    "underlying": underlying_marks,
                    "option_n": len(live_marks.get("option") or {}),
                },
            )
        except Exception as exc:  # noqa: BLE001
            append_audit("manage_marks_error", payload={"error": str(exc)})

    try:
        opt_loss = float(os.getenv("TRADING_AGENT_OPTION_LOSS_PCT", "50") or 50)
    except ValueError:
        opt_loss = 50.0
    try:
        opt_profit = float(os.getenv("TRADING_AGENT_OPTION_PROFIT_PCT", "100") or 100)
    except ValueError:
        opt_profit = 100.0

    from trading_agent.oms.manage_rules import (
        capture_option_premium,
        early_exit_reasons,
        update_trail_stop,
    )

    for lot in open_lots:
        und = underlying_marks.get(lot.symbol.upper())
        occ_key = (lot.occ_symbol or "").strip()
        opt_mark = marks.get(occ_key) or marks.get(occ_key.upper())
        mark = float(opt_mark or und or 0.0)

        def _row(action: str, reason_s: str = "", **extra) -> Dict[str, Any]:
            """Paper Discord-friendly manage row + upstream fields."""
            strikes = lot.strike_prices or []
            strike_s = ""
            if strikes:
                try:
                    strike_s = "/".join(f"{float(s):g}" for s in strikes[:3])
                except (TypeError, ValueError):
                    strike_s = ",".join(str(s) for s in strikes[:3])
            row = {
                "lot_id": lot.lot_id,
                "lot_id_short": (lot.lot_id or "")[-6:],
                "symbol": lot.symbol,
                "action": action,
                "reason": reason_s,
                "status": lot.status,
                "side": lot.side or "",
                "instrument": lot.instrument or "",
                "strategy": lot.strategy or "",
                "setup_id": lot.setup_id or "",
                "quantity": lot.quantity,
                "entry": lot.entry,
                "stop": lot.stop,
                "target": lot.target,
                "expiration": lot.expiration or "",
                "occ_symbol": lot.occ_symbol or "",
                "strikes": strike_s,
                "mark": float(mark or 0) or None,
                "underlying": float(und) if und is not None else None,
                "option_mark": opt_mark,
            }
            row.update(extra)
            return row

        # Option entry premium: broker avg → lot meta → small fill_entry
        opt_entry: Optional[float] = None
        if occ_key and pos_index:
            row = pos_index.get(occ_key) or pos_index.get(occ_key.upper())
            if isinstance(row, dict):
                try:
                    from trading_agent.oms.broker import position_avg_price

                    avg = position_avg_price(row)
                    if avg > 0 and avg < 50:
                        opt_entry = avg
                        capture_option_premium(lot, premium=avg, source="broker_avg")
                except Exception:
                    pass
        if opt_entry is None:
            meta = lot.broker_meta or {}
            for key in ("option_entry_premium", "entry_option_price", "option_mark_at_entry"):
                try:
                    v = float(meta.get(key) or 0)
                except (TypeError, ValueError):
                    v = 0.0
                if 0 < v < 50:
                    opt_entry = v
                    break
        if opt_entry is None:
            fe = float(lot.fill_entry or 0)
            if 0 < fe < 50:
                opt_entry = fe

        trail_info: Dict[str, Any] = {}
        if und and und > 0:
            try:
                trail_info = update_trail_stop(lot, underlying_price=float(und))
                if trail_info.get("trailed"):
                    store.upsert_lot(lot)
                    append_audit(
                        "trail_stop_updated",
                        payload={"lot_id": lot.lot_id, "symbol": lot.symbol, **trail_info},
                    )
            except Exception as trail_exc:  # noqa: BLE001
                append_audit(
                    "trail_stop_error",
                    payload={"lot_id": lot.lot_id, "error": str(trail_exc)},
                )

        should, reason = early_exit_reasons(
            lot,
            option_mark=float(opt_mark) if opt_mark else None,
            option_entry=opt_entry,
        )
        if not should:
            should, reason = should_exit_lot(
                lot,
                mark_price=float(mark or 0),
                underlying_price=und,
                option_mark=float(opt_mark) if opt_mark else None,
                option_entry=opt_entry,
                option_loss_pct=opt_loss,
                option_profit_pct=opt_profit,
            )
        if should:
            exit_px = float(opt_mark or und or mark or 0)
            closed = close_lot(
                store,
                lot,
                live=live,
                call_mcp=call_mcp,
                reason=reason,
                exit_price=exit_px,
            )
            # Expired / EOD / near-expiry / wipe: if broker close fails, still clear OMS lot
            if closed.status not in (
                LotStatus.CLOSED.value,
            ) and reason.startswith(
                ("expired_option", "eod_0dte", "near_expiry_flatten", "min_premium_wipe")
            ):
                try:
                    from trading_agent.oms.lifecycle import close_lot_as_orphan

                    closed = close_lot_as_orphan(
                        store, lot, reason=f"{reason}:broker_close_failed"
                    )
                except Exception as orphan_exc:  # noqa: BLE001
                    append_audit(
                        "orphan_after_exit_fail",
                        payload={"lot_id": lot.lot_id, "error": str(orphan_exc)},
                    )
            pnl_est = None
            if opt_entry and opt_mark and opt_entry < 50:
                pnl_est = (float(opt_mark) - float(opt_entry)) * int(lot.quantity or 1) * 100.0
            row = _row("exit", reason or "", option_entry=opt_entry, pnl_est=pnl_est)
            row["status"] = closed.status
            results.append(row)
        else:
            results.append(
                _row(
                    "hold",
                    "",
                    option_entry=opt_entry,
                    trail=trail_info or None,
                )
            )
    store.save()
    return results


def manage_enabled() -> bool:
    return os.getenv("TRADING_AGENT_OMS_MANAGE", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
