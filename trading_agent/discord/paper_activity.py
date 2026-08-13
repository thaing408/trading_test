"""Paper / trading_test Discord activity feed (entries, exits, positions, EOD).

Posts to DISCORD_CHANNEL_ID (or DISCORD_PAPER_CHANNEL_ID). Forces bot-channel
mode (ignores production webhook) so paper traffic stays on the paper channel.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from zoneinfo import ZoneInfo

from trading_agent.discord.config import DiscordConfig
from trading_agent.discord.poster import DiscordPostError, post_message

PT = ZoneInfo("America/Los_Angeles")

# Default paper journal channel (user-specified)
DEFAULT_PAPER_CHANNEL_ID = "1536602374502613013"


def paper_channel_id() -> str:
    return (
        os.getenv("DISCORD_PAPER_CHANNEL_ID")
        or os.getenv("DISCORD_CHANNEL_ID")
        or DEFAULT_PAPER_CHANNEL_ID
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
) -> List[dict]:
    """Post markdown content to the paper Discord channel."""
    if not activity_enabled():
        return []
    cfg = paper_discord_config()
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


def fetch_ibkr_positions() -> List[Dict[str, Any]]:
    """Best-effort IBKR open positions for paper account."""
    try:
        from trading_agent.oms.ibkr_broker import ibkr_trade_config
        from ib_insync import IB
    except ImportError:
        return []
    cfg = ibkr_trade_config()
    if not cfg.get("enabled"):
        return []
    ib = IB()
    try:
        ib.connect(
            cfg["host"],
            int(cfg["port"]),
            clientId=int(cfg["client_id"]) + 50,
            timeout=float(cfg.get("timeout") or 15),
            readonly=True,
        )
        rows: List[Dict[str, Any]] = []
        for pos in ib.positions():
            c = pos.contract
            rows.append(
                {
                    "symbol": getattr(c, "symbol", None) or getattr(c, "localSymbol", "?"),
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


def post_positions(*, source: str = "IBKR paper") -> List[dict]:
    positions = fetch_ibkr_positions()
    body = format_positions_snapshot(positions)
    return post_activity(body, title=f"Positions · {source}")


def build_eod_summary(
    *,
    trading_date: str | None = None,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    """Assemble end-of-day summary from local paper state + IBKR positions."""
    day = trading_date or datetime.now(PT).date().isoformat()
    sync = Path(os.getenv("TRADING_AGENT_SYNC_DIR") or Path.home() / ".trading_test" / "sync")
    state_dir = Path.home() / ".trading_test"
    lines = [
        f"**Trading date:** {day}",
        f"**Broker:** {os.getenv('TRADING_AGENT_BROKER', 'ibkr')}",
        f"**Account:** {os.getenv('IBKR_ACCOUNT', 'paper')}",
        f"**CIO:** {'on' if os.getenv('TRADING_AGENT_INCLUDE_CIO','0') in ('1','true') else 'off'}",
        "",
    ]

    book_path = sync / "auto_trade_book.json"
    if book_path.is_file():
        try:
            book = json.loads(book_path.read_text(encoding="utf-8"))
            entries = book.get("entries") or []
            lines.append(f"**Auto-trade book:** {len(entries)} ENTER row(s)")
            lines.append(f"stay_in_cash={book.get('stay_in_cash')}")
            for e in entries[:12]:
                lines.append(
                    f"- {e.get('symbol')} {e.get('side')} "
                    f"entry={e.get('entry')} stop={e.get('stop')} "
                    f"src={e.get('source') or e.get('setup_id')}"
                )
            if len(entries) > 12:
                lines.append(f"- … +{len(entries)-12} more")
        except (OSError, json.JSONDecodeError):
            lines.append("_auto_trade_book unreadable_")
    else:
        lines.append("_No auto_trade_book.json_")

    lines.append("")
    lines.append("**Open positions (IBKR)**")
    lines.append(format_positions_snapshot(fetch_ibkr_positions()))

    # Ready orders archive today
    ready_dir = state_dir / "ready_orders"
    if not ready_dir.is_dir():
        ready_dir = Path.home() / ".trading_agent" / "ready_orders"
    if ready_dir.is_dir():
        today_files = sorted(ready_dir.glob(f"*{day}*"))[-5:]
        if today_files:
            lines.append("")
            lines.append(f"**Ready-order files today:** {len(list(ready_dir.glob(f'*{day}*')))}")

    if extra:
        lines.append("")
        lines.append("**Extra**")
        for k, v in extra.items():
            lines.append(f"- {k}: {v}")

    lines.append("")
    lines.append("_Paper trading test — not production Schwab desk._")
    return "\n".join(lines)


def post_eod_summary(*, trading_date: str | None = None, extra: Optional[Dict[str, Any]] = None) -> List[dict]:
    return post_activity(
        build_eod_summary(trading_date=trading_date, extra=extra),
        title="📊 EOD Summary · Paper",
    )
