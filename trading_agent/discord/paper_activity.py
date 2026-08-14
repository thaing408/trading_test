"""Paper / trading_test Discord activity feed (entries, exits, positions, EOD).

Posts to DISCORD_CHANNEL_ID (or DISCORD_PAPER_CHANNEL_ID). Forces bot-channel
mode (ignores production webhook) so paper traffic stays on the paper channel.

EOD P/L journal (like prod #trading-journal) posts to **#ibkr-tradings** via
``DISCORD_IBKR_CHANNEL_ID`` when set.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from trading_agent.discord.config import DiscordConfig
from trading_agent.discord.poster import DiscordPostError, post_message

PT = ZoneInfo("America/Los_Angeles")
ET = ZoneInfo("America/New_York")

# Default paper journal channel (user-specified)
DEFAULT_PAPER_CHANNEL_ID = "1536602374502613013"
# #ibkr-tradings — set DISCORD_IBKR_CHANNEL_ID in env (required for EOD journal target)
DEFAULT_IBKR_CHANNEL_ID = ""  # filled via env; no hardcode unless user provides


def paper_channel_id() -> str:
    return (
        os.getenv("DISCORD_PAPER_CHANNEL_ID")
        or os.getenv("DISCORD_CHANNEL_ID")
        or DEFAULT_PAPER_CHANNEL_ID
    ).strip()


def ibkr_journal_channel_id() -> str:
    """Channel for paper EOD P/L journal (#ibkr-tradings)."""
    return (
        os.getenv("DISCORD_IBKR_CHANNEL_ID")
        or os.getenv("DISCORD_IBKR_TRADINGS_CHANNEL_ID")
        or os.getenv("DISCORD_PAPER_EOD_CHANNEL_ID")
        or paper_channel_id()
    ).strip()


def paper_discord_config() -> DiscordConfig:
    """Bot + paper channel only (never production webhook)."""
    token = (
        os.getenv("DISCORD_TOKEN")
        or os.getenv("DISCORD_BOT_TOKEN")
        or ""
    ).strip() or None
    return DiscordConfig(
        webhook_url=None,
        bot_token=token,
        channel_id=paper_channel_id(),
    )


def ibkr_journal_discord_config() -> DiscordConfig:
    """Bot + #ibkr-tradings (EOD P/L), never production webhook."""
    token = (
        os.getenv("DISCORD_TOKEN")
        or os.getenv("DISCORD_BOT_TOKEN")
        or ""
    ).strip() or None
    return DiscordConfig(
        webhook_url=None,
        bot_token=token,
        channel_id=ibkr_journal_channel_id() or paper_channel_id(),
    )


def activity_enabled() -> bool:
    if os.getenv("TRADING_AGENT_NO_DISCORD", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return False
    if os.getenv("TRADING_AGENT_DRY_RUN", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return False
    cfg = paper_discord_config()
    return cfg.has_delivery()


def post_activity(
    content: str,
    *,
    title: str = "Paper activity",
    username: str = "Paper Trading Test",
    channel: str = "paper",
) -> List[dict]:
    """Post markdown content to the paper Discord channel.

    channel: ``paper`` (default activity) or ``ibkr`` (#ibkr-tradings EOD journal).
    """
    if not activity_enabled():
        return []
    cfg = ibkr_journal_discord_config() if channel == "ibkr" else paper_discord_config()
    if not cfg.channel_id:
        return [{"error": "no Discord channel id", "title": title}]
    header = f"**{title}** · {datetime.now(PT).strftime('%Y-%m-%d %H:%M %Z')}\n"
    body = header + content
    try:
        return post_message(body, cfg, username=username)
    except DiscordPostError as exc:
        return [{"error": str(exc), "title": title}]

def format_order_activity(order: Any, *, event: str) -> str:
    """Format ReadyOrder-like object for enter/exit/submit events."""
    status = getattr(order, "status", "") or ""
    symbol = getattr(order, "symbol", "") or ""
    action = getattr(order, "action", "") or ""
    side = getattr(order, "side", "") or ""
    strategy = getattr(order, "strategy", "") or ""
    setup = getattr(order, "setup_id", "") or ""
    entry = getattr(order, "entry", 0)
    stop = getattr(order, "stop", 0)
    target = getattr(order, "target", 0)
    qty = getattr(order, "quantity", 0)
    risk = getattr(order, "max_risk_dollars", 0)
    broker = {}
    br = getattr(order, "broker_response", None)
    if isinstance(br, dict):
        broker = br
    lines = [
        f"**{event}** `{status}` · **{symbol}**",
        f"action={action} side={side} qty={qty}",
        f"strategy={strategy} setup={setup}",
        f"entry={entry} stop={stop} target={target} risk$={risk}",
    ]
    if broker:
        mode = broker.get("mode") or broker.get("status") or broker.get("error")
        bro = broker.get("broker") or os.getenv("TRADING_AGENT_BROKER", "")
        lines.append(f"broker={bro} result={mode}")
        if broker.get("message"):
            lines.append(f"_{str(broker.get('message'))[:200]}_")
        if broker.get("order_id") is not None:
            lines.append(f"order_id={broker.get('order_id')}")
    skip = getattr(order, "skip_reason", "") or ""
    if skip:
        lines.append(f"skip={skip}")
    return "\n".join(lines)


def post_order_event(order: Any, *, event: str) -> List[dict]:
    emoji = {
        "ENTER": "🟢",
        "EXIT": "🔴",
        "SUBMITTED": "✅",
        "DRY_RUN": "🧪",
        "FAILED": "⛔",
        "SKIPPED": "⬜",
        "READY": "📋",
    }.get(event.upper(), "•")
    return post_activity(
        format_order_activity(order, event=f"{emoji} {event}"),
        title=f"Order · {event}",
    )


def post_orders_batch(orders: Sequence[Any], *, label: str = "Consumer cycle") -> List[dict]:
    if not orders:
        return post_activity("_No orders this cycle._", title=label)
    lines = [f"**{len(orders)}** order(s)\n"]
    for o in orders:
        st = getattr(o, "status", "?")
        sym = getattr(o, "symbol", "?")
        act = getattr(o, "action", "?")
        lines.append(f"- `{st}` **{sym}** {act} {getattr(o, 'side', '')}")
    return post_activity("\n".join(lines), title=label)


def format_positions_snapshot(positions: Sequence[Dict[str, Any]]) -> str:
    if not positions:
        return "_Flat — no open positions._"
    lines = ["```", f"{'SYM':<10} {'QTY':>8} {'AVG':>10} {'MKT':>10}", "-" * 42]
    for p in positions:
        sym = str(p.get("symbol") or p.get("localSymbol") or "?")[:10]
        qty = p.get("quantity") or p.get("position") or p.get("longQuantity") or 0
        avg = p.get("average_price") or p.get("avgCost") or p.get("averageCost") or 0
        mkt = p.get("market_value") or p.get("marketValue") or ""
        try:
            lines.append(f"{sym:<10} {float(qty):>8.2f} {float(avg):>10.2f} {str(mkt)[:10]:>10}")
        except (TypeError, ValueError):
            lines.append(f"{sym:<10} {qty!s:>8} {avg!s:>10} {str(mkt)[:10]:>10}")
    lines.append("```")
    return "\n".join(lines)


def _connect_ibkr_readonly(client_offset: int = 50):
    """Connect IBKR readonly; returns (IB, cfg) or (None, error_str)."""
    try:
        from trading_agent.oms.ibkr_broker import ibkr_trade_config
        from ib_insync import IB
    except ImportError as exc:
        return None, f"import: {exc}"
    cfg = ibkr_trade_config()
    if not cfg.get("enabled"):
        cfg = {
            **cfg,
            "enabled": True,
            "host": os.getenv("IBKR_HOST", "127.0.0.1"),
            "port": int(os.getenv("IBKR_PORT", "4002") or 4002),
            "client_id": int(os.getenv("IBKR_CLIENT_ID", "17") or 17),
            "timeout": 15.0,
            "account": (os.getenv("IBKR_ACCOUNT") or "").strip(),
        }
    ib = IB()
    try:
        ib.connect(
            cfg["host"],
            int(cfg["port"]),
            clientId=int(cfg["client_id"]) + int(client_offset),
            timeout=float(cfg.get("timeout") or 15),
            readonly=True,
        )
        if not ib.isConnected():
            return None, "not connected"
        return ib, cfg
    except Exception as exc:  # noqa: BLE001
        try:
            ib.disconnect()
        except Exception:  # noqa: BLE001
            pass
        return None, str(exc)


def fetch_ibkr_positions() -> List[Dict[str, Any]]:
    """Best-effort IBKR open positions for paper account."""
    ib, cfg = _connect_ibkr_readonly(51)
    if ib is None:
        return []
    try:
        rows: List[Dict[str, Any]] = []
        # portfolio() has marketPrice / marketValue / unrealizedPNL when available
        for item in ib.portfolio():
            c = item.contract
            rows.append(
                {
                    "symbol": getattr(c, "localSymbol", None)
                    or getattr(c, "symbol", "?"),
                    "localSymbol": getattr(c, "localSymbol", ""),
                    "quantity": float(item.position),
                    "average_price": float(item.averageCost or 0),
                    "market_price": float(getattr(item, "marketPrice", 0) or 0),
                    "market_value": float(getattr(item, "marketValue", 0) or 0),
                    "unrealized_pnl": float(getattr(item, "unrealizedPNL", 0) or 0),
                    "realized_pnl": float(getattr(item, "realizedPNL", 0) or 0),
                    "account": item.account,
                    "secType": getattr(c, "secType", ""),
                }
            )
        if not rows:
            for pos in ib.positions():
                c = pos.contract
                rows.append(
                    {
                        "symbol": getattr(c, "symbol", None)
                        or getattr(c, "localSymbol", "?"),
                        "localSymbol": getattr(c, "localSymbol", ""),
                        "quantity": float(pos.position),
                        "average_price": float(pos.avgCost or 0),
                        "account": pos.account,
                        "secType": getattr(c, "secType", ""),
                    }
                )
        ib.disconnect()
        return [r for r in rows if abs(float(r.get("quantity") or 0)) > 1e-9]
    except Exception:  # noqa: BLE001
        try:
            ib.disconnect()
        except Exception:  # noqa: BLE001
            pass
        return []


def fetch_ibkr_day_pnl(
    *,
    trading_date: str | None = None,
) -> Dict[str, Any]:
    """Pull day P/L snapshot from IBKR paper (account + fills) for EOD journal.

    Mirrors production journal shape: realized / unrealized / net, W-L, fills list.
    """
    day = trading_date or datetime.now(PT).date().isoformat()
    try:
        day_d = date.fromisoformat(day)
    except ValueError:
        day_d = datetime.now(PT).date()

    out: Dict[str, Any] = {
        "trading_date": day,
        "account": os.getenv("IBKR_ACCOUNT", "") or "",
        "connected": False,
        "error": "",
        "nav": None,
        "cash": None,
        "stock_value": None,
        "available_funds": None,
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "daily_pnl": None,
        "gross_fills_pnl": 0.0,
        "commissions": 0.0,
        "fills": [],
        "positions": [],
        "wins": 0,
        "losses": 0,
    }

    ib, cfg = _connect_ibkr_readonly(52)
    if ib is None:
        out["error"] = str(cfg)
        return out
    try:
        out["connected"] = True
        accts = ib.managedAccounts() or []
        acct = (cfg.get("account") if isinstance(cfg, dict) else "") or (
            accts[0] if accts else ""
        )
        out["account"] = acct or out["account"]

        # Account summary tags
        tag_map = {
            "NetLiquidation": "nav",
            "TotalCashValue": "cash",
            "StockMarketValue": "stock_value",
            "AvailableFunds": "available_funds",
            "RealizedPnL": "realized_pnl",
            "UnrealizedPnL": "unrealized_pnl",
            "DailyPnL": "daily_pnl",
        }
        for v in ib.accountValues(acct) if acct else ib.accountValues():
            key = tag_map.get(v.tag)
            if not key:
                continue
            try:
                val = float(v.value)
            except (TypeError, ValueError):
                continue
            if key in ("realized_pnl", "unrealized_pnl") and v.currency not in (
                "USD",
                "",
                None,
            ):
                continue
            out[key] = val

        # Portfolio unrealized sum if tag missing
        positions = []
        u_sum = 0.0
        r_sum = 0.0
        for item in ib.portfolio():
            c = item.contract
            u = float(getattr(item, "unrealizedPNL", 0) or 0)
            r = float(getattr(item, "realizedPNL", 0) or 0)
            u_sum += u
            r_sum += r
            positions.append(
                {
                    "symbol": getattr(c, "localSymbol", None)
                    or getattr(c, "symbol", "?"),
                    "quantity": float(item.position),
                    "average_price": float(item.averageCost or 0),
                    "market_price": float(getattr(item, "marketPrice", 0) or 0),
                    "market_value": float(getattr(item, "marketValue", 0) or 0),
                    "unrealized_pnl": u,
                    "realized_pnl": r,
                    "secType": getattr(c, "secType", ""),
                }
            )
        out["positions"] = [p for p in positions if abs(p["quantity"]) > 1e-9]
        if out.get("unrealized_pnl") in (None, 0.0) and u_sum:
            out["unrealized_pnl"] = u_sum
        # Realized from portfolio is session-ish; prefer account RealizedPnL

        # Executions / fills for the US session day (ET calendar)
        fills_out: List[Dict[str, Any]] = []
        try:
            from ib_insync import ExecutionFilter

            # IB filter time is exchange local; use midnight ET of trading day
            start_et = datetime.combine(day_d, time(0, 0), tzinfo=ET)
            filt = ExecutionFilter()
            filt.time = start_et.strftime("%Y%m%d-00:00:00")
            if acct:
                filt.acctCode = acct
            execs = ib.reqExecutions(filt)
            ib.sleep(1.5)
            # Also scan ib.fills() for same day
            seen = set()
            for fill in list(execs) + list(ib.fills()):
                ex = fill.execution
                cr = fill.commissionReport
                c = fill.contract
                exec_id = getattr(ex, "execId", "") or ""
                if exec_id and exec_id in seen:
                    continue
                if exec_id:
                    seen.add(exec_id)
                # time filter
                tstr = str(getattr(ex, "time", "") or "")
                # keep if date matches day_d in ET
                keep = True
                try:
                    if hasattr(ex.time, "astimezone"):
                        et_d = ex.time.astimezone(ET).date()
                        keep = et_d == day_d
                    elif tstr:
                        keep = day_d.isoformat().replace("-", "") in tstr.replace(
                            "-", ""
                        ) or day_d.isoformat() in tstr
                except Exception:  # noqa: BLE001
                    keep = True
                if not keep:
                    continue
                rpnl = float(getattr(cr, "realizedPNL", 0) or 0) if cr else 0.0
                comm = float(getattr(cr, "commission", 0) or 0) if cr else 0.0
                if cr and getattr(cr, "commission", None) is not None:
                    # commission often positive cost
                    pass
                fills_out.append(
                    {
                        "symbol": getattr(c, "localSymbol", None)
                        or getattr(c, "symbol", "?"),
                        "side": getattr(ex, "side", ""),
                        "qty": float(getattr(ex, "shares", 0) or 0),
                        "price": float(getattr(ex, "price", 0) or 0),
                        "realized_pnl": rpnl,
                        "commission": comm,
                        "time": tstr,
                        "secType": getattr(c, "secType", ""),
                    }
                )
                out["gross_fills_pnl"] = float(out["gross_fills_pnl"]) + rpnl
                out["commissions"] = float(out["commissions"]) + abs(comm)
                if rpnl > 1e-6:
                    out["wins"] = int(out["wins"]) + 1
                elif rpnl < -1e-6:
                    out["losses"] = int(out["losses"]) + 1
        except Exception as fill_exc:  # noqa: BLE001
            out["fills_error"] = str(fill_exc)

        out["fills"] = fills_out
        # Prefer sum of fill realized if account realized looks empty but fills exist
        if fills_out and (
            out.get("realized_pnl") in (None, 0.0)
            or abs(float(out.get("gross_fills_pnl") or 0))
            > abs(float(out.get("realized_pnl") or 0))
        ):
            out["realized_pnl"] = float(out["gross_fills_pnl"])

        # Net day = realized + unrealized change; DailyPnL when IB provides it
        real = float(out.get("realized_pnl") or 0)
        unrl = float(out.get("unrealized_pnl") or 0)
        if out.get("daily_pnl") is None:
            out["daily_pnl"] = real  # conservative: realized day; unrealized shown separate
        out["net_day_pnl"] = (
            float(out["daily_pnl"])
            if out.get("daily_pnl") is not None
            else real + unrl
        )

        ib.disconnect()
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
        try:
            ib.disconnect()
        except Exception:  # noqa: BLE001
            pass
    return out


def _fmt_money(x: Any) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "n/a"
    sign = "+" if v >= 0 else "-"
    return f"{sign}${abs(v):,.2f}"


def format_positions_snapshot(positions: Sequence[Dict[str, Any]]) -> str:
    if not positions:
        return "_Flat — no open positions._"
    lines = [
        "```",
        f"{'SYM':<12} {'QTY':>8} {'AVG':>10} {'MKT':>10} {'uPNL':>10}",
        "-" * 54,
    ]
    for p in positions:
        sym = str(p.get("symbol") or p.get("localSymbol") or "?")[:12]
        qty = p.get("quantity") or p.get("position") or p.get("longQuantity") or 0
        avg = p.get("average_price") or p.get("avgCost") or p.get("averageCost") or 0
        mkt = p.get("market_price") or p.get("market_value") or ""
        upnl = p.get("unrealized_pnl")
        try:
            up = f"{float(upnl):+.2f}" if upnl is not None else ""
            lines.append(
                f"{sym:<12} {float(qty):>8.2f} {float(avg):>10.2f} "
                f"{str(mkt)[:10]:>10} {up:>10}"
            )
        except (TypeError, ValueError):
            lines.append(f"{sym:<12} {qty!s:>8} {avg!s:>10} {str(mkt)[:10]:>10}")
    lines.append("```")
    return "\n".join(lines)


def build_pnl_journal(
    *,
    trading_date: str | None = None,
    pnl: Optional[Dict[str, Any]] = None,
) -> str:
    """Production-style day P/L journal markdown for IBKR paper."""
    day = trading_date or datetime.now(PT).date().isoformat()
    data = pnl or fetch_ibkr_day_pnl(trading_date=day)
    real = float(data.get("realized_pnl") or 0)
    unrl = float(data.get("unrealized_pnl") or 0)
    daily = data.get("daily_pnl")
    if daily is None:
        daily = real
    daily_f = float(daily)
    wins = int(data.get("wins") or 0)
    losses = int(data.get("losses") or 0)
    fills = list(data.get("fills") or [])
    positions = list(data.get("positions") or [])

    # Split fill realized into gains vs losses totals
    gain_sum = sum(float(f.get("realized_pnl") or 0) for f in fills if float(f.get("realized_pnl") or 0) > 0)
    loss_sum = sum(float(f.get("realized_pnl") or 0) for f in fills if float(f.get("realized_pnl") or 0) < 0)

    lines = [
        f"=== IBKR PAPER JOURNAL — {day} PT ===",
        "",
        f"**Account:** `{data.get('account') or os.getenv('IBKR_ACCOUNT', 'paper')}`",
        f"**Connected:** {data.get('connected')}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "**DAY P/L**",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"**Day realized:** {_fmt_money(real)}",
        f"**Day unrealized (open):** {_fmt_money(unrl)}",
        f"**Day net (IB daily / est.):** {_fmt_money(daily_f)}",
        f"**Gains (fill RP&L > 0):** {_fmt_money(gain_sum)}",
        f"**Losses (fill RP&L < 0):** {_fmt_money(loss_sum)}",
        f"**Commissions:** {_fmt_money(data.get('commissions'))}",
        f"**W/L fills:** {wins}W – {losses}L  |  **fills:** {len(fills)}",
        "",
    ]
    if data.get("nav") is not None:
        lines.append(f"**NAV:** {_fmt_money(data.get('nav')).lstrip('+')}")
    if data.get("cash") is not None:
        lines.append(f"**Cash:** {_fmt_money(data.get('cash')).lstrip('+')}")
    if data.get("stock_value") is not None:
        lines.append(f"**Stock value:** {_fmt_money(data.get('stock_value')).lstrip('+')}")
    if data.get("available_funds") is not None:
        lines.append(
            f"**Available funds:** {_fmt_money(data.get('available_funds')).lstrip('+')}"
        )

    if fills:
        lines.extend(
            [
                "",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "**FILLS / REALIZED TODAY**",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "",
            ]
        )
        for i, f in enumerate(fills[:25], 1):
            rp = float(f.get("realized_pnl") or 0)
            icon = "✅" if rp >= 0 else "❌"
            lines.append(
                f"#{i} **{f.get('symbol')}** {f.get('side')} "
                f"qty={f.get('qty')} @{float(f.get('price') or 0):.2f}  "
                f"| {_fmt_money(rp)} {icon}"
            )
        if len(fills) > 25:
            lines.append(f"_… +{len(fills) - 25} more fills_")
    else:
        lines.extend(["", "_No closed-fill realized P/L rows for today (or no trades)._", ""])

    lines.extend(
        [
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "**OPEN POSITIONS**",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            format_positions_snapshot(positions),
            "",
            f"**Summary:** Net day {_fmt_money(daily_f)}  |  "
            f"Realized {_fmt_money(real)}  |  Unrealized {_fmt_money(unrl)}  |  "
            f"{wins}W-{losses}L",
            "",
            "_Source: IBKR paper API (auto EOD). Not production Schwab desk._",
        ]
    )
    if data.get("error"):
        lines.append(f"_Note: {data.get('error')}_")
    if data.get("fills_error"):
        lines.append(f"_Fills: {data.get('fills_error')}_")
    return "\n".join(lines)


def post_positions(*, source: str = "IBKR paper") -> List[dict]:
    positions = fetch_ibkr_positions()
    body = format_positions_snapshot(positions)
    return post_activity(body, title=f"Positions · {source}")


def build_eod_summary(
    *,
    trading_date: str | None = None,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    """Assemble end-of-day summary: P/L journal + book context."""
    day = trading_date or datetime.now(PT).date().isoformat()
    # Primary: production-style P/L block
    pnl = fetch_ibkr_day_pnl(trading_date=day)
    lines = [build_pnl_journal(trading_date=day, pnl=pnl), ""]

    sync = Path(os.getenv("TRADING_AGENT_SYNC_DIR") or Path.home() / ".trading_test" / "sync")
    book_path = sync / "auto_trade_book.json"
    if book_path.is_file():
        try:
            book = json.loads(book_path.read_text(encoding="utf-8"))
            entries = book.get("entries") or []
            lines.append(
                f"**Auto-trade book:** {len(entries)} ENTER · "
                f"stay_in_cash={book.get('stay_in_cash')}"
            )
        except (OSError, json.JSONDecodeError):
            pass

    if extra:
        lines.append("**Extra**")
        for k, v in extra.items():
            lines.append(f"- {k}: {v}")

    return "\n".join(lines)


def post_eod_summary(
    *,
    trading_date: str | None = None,
    extra: Optional[Dict[str, Any]] = None,
    to_ibkr_channel: bool = True,
) -> List[dict]:
    """Post EOD P/L journal to #ibkr-tradings (and optional paper channel)."""
    body = build_eod_summary(trading_date=trading_date, extra=extra)
    results: List[dict] = []
    # Primary: #ibkr-tradings
    if to_ibkr_channel:
        results.extend(
            post_activity(
                body,
                title="📊 IBKR Paper EOD · P/L Journal",
                username="IBKR Paper Journal",
                channel="ibkr",
            )
        )
    # Also mirror to paper activity channel if different
    ibkr_ch = ibkr_journal_channel_id()
    paper_ch = paper_channel_id()
    if paper_ch and ibkr_ch and paper_ch != ibkr_ch:
        results.extend(
            post_activity(
                body,
                title="📊 EOD Summary · Paper",
                username="Paper Trading Test",
                channel="paper",
            )
        )
    elif not to_ibkr_channel:
        results.extend(
            post_activity(
                body,
                title="📊 EOD Summary · Paper",
                username="Paper Trading Test",
                channel="paper",
            )
        )
    return results
