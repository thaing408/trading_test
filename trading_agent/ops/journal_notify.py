"""Post auto-trade activity to Discord #trading-journal with @mention.

Uses bot API (not webhook) so user pings actually notify. Config from
~/.grok/discord.env (loaded by consumer):

  DISCORD_BOT_TOKEN / DISCORD_TOKEN
  DISCORD_JOURNAL_CHANNEL_ID   (default #trading-journal)
  DISCORD_JOURNAL_MENTION_USER_ID

Disable: TRADING_AGENT_JOURNAL_ALERTS=0
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")

DEFAULT_JOURNAL_CHANNEL = "1514644765797515426"
DEFAULT_MENTION_USER = "493638750086365194"


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name, "1" if default else "0").strip().lower()
    if default:
        return raw not in ("0", "false", "no", "off")
    return raw in ("1", "true", "yes", "on")


def _token() -> str:
    return (
        os.getenv("DISCORD_BOT_TOKEN", "").strip()
        or os.getenv("DISCORD_TOKEN", "").strip()
    )


def _channel_id() -> str:
    return (
        os.getenv("DISCORD_JOURNAL_CHANNEL_ID", "").strip()
        or DEFAULT_JOURNAL_CHANNEL
    )


def _mention_user_id() -> str:
    return (
        os.getenv("DISCORD_JOURNAL_MENTION_USER_ID", "").strip()
        or DEFAULT_MENTION_USER
    )


def _dedupe_path() -> Path:
    raw = os.getenv("TRADING_AGENT_JOURNAL_DEDUPE_FILE", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".trading_agent" / "journal_activity_posted.json"


def _already_posted(key: str) -> bool:
    if not key:
        return False
    path = _dedupe_path()
    try:
        if not path.is_file():
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
        keys = data if isinstance(data, list) else list(data.get("keys") or [])
        return key in keys
    except (OSError, json.JSONDecodeError, TypeError):
        return False


def _mark_posted(key: str) -> None:
    if not key:
        return
    path = _dedupe_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    keys: List[str] = []
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            keys = data if isinstance(data, list) else list(data.get("keys") or [])
    except (OSError, json.JSONDecodeError, TypeError):
        keys = []
    if key not in keys:
        keys.append(key)
    path.write_text(json.dumps(keys[-400:], indent=2) + "\n", encoding="utf-8")


def post_journal_activity(
    message: str,
    *,
    title: str = "Auto-trade",
    mention: bool = True,
    dedupe_key: str = "",
    force: bool = False,
) -> Dict[str, Any]:
    """Post a short activity line to #trading-journal. Fail-open on errors."""
    if not force and not _env_bool("TRADING_AGENT_JOURNAL_ALERTS", True):
        return {"skipped": True, "reason": "journal_alerts_disabled"}

    if dedupe_key and _already_posted(dedupe_key):
        return {"skipped": True, "reason": "duplicate", "dedupe_key": dedupe_key}

    token = _token()
    channel = _channel_id()
    if not token or not channel:
        return {"error": "missing_discord_token_or_journal_channel"}

    when = datetime.now(PT).strftime("%Y-%m-%d %H:%M %Z")
    body = f"**{title}** · `{when}`\n{message}".strip()
    mention_id = _mention_user_id() if mention else ""
    if mention_id:
        content = f"<@{mention_id}>\n{body}"
    else:
        content = body
    if len(content) > 1900:
        content = content[:1890] + "…"

    payload: Dict[str, Any] = {"content": content}
    if mention_id:
        payload["allowed_mentions"] = {"users": [mention_id]}

    url = f"https://discord.com/api/v10/channels/{channel}/messages"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "trading-agent-journal/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if dedupe_key:
                _mark_posted(dedupe_key)
            return {"ok": True, "status": resp.status, "text": raw[:120]}
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")[:300]
        return {"error": f"http_{exc.code}", "detail": err}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def notify_order_activity(order: Any, *, live: bool = True) -> Dict[str, Any]:
    """Notify for a ReadyOrder-like object after place (submitted/failed)."""
    if not live:
        return {"skipped": True, "reason": "not_live"}

    status = str(getattr(order, "status", "") or "").lower()
    if status not in ("submitted", "failed"):
        # also accept dict shape from result["orders"]
        if isinstance(order, dict):
            status = str(order.get("status") or "").lower()
        if status not in ("submitted", "failed"):
            return {"skipped": True, "reason": f"status_{status}"}

    def _g(key: str, default: Any = "") -> Any:
        if isinstance(order, dict):
            return order.get(key, default)
        return getattr(order, key, default)

    sym = str(_g("symbol") or "?").upper()
    strategy = str(_g("strategy") or _g("setup_id") or "")[:80]
    side = str(_g("side") or "")
    qty = _g("quantity") or 1
    risk = _g("max_risk_dollars")
    exp = _g("expiration") or ""
    strikes = _g("strike_prices") or []
    skip = _g("skip_reason") or ""
    broker = _g("broker_response") or {}
    occ = ""
    if isinstance(broker, dict):
        occ = str(broker.get("occ_symbol") or broker.get("symbol") or "")

    if status == "submitted":
        emoji = "🟢"
        head = "ENTRY SUBMITTED"
    else:
        emoji = "⚠️"
        head = "ENTRY FAILED"

    lines = [
        f"{emoji} **{head}** **{sym}**",
        f"Status: `{status}` · qty={qty} · side={side or '—'}",
    ]
    if strategy:
        lines.append(f"Setup: {strategy}")
    if strikes:
        lines.append(f"Strikes: {strikes} exp={exp or '—'}")
    if occ:
        lines.append(f"OCC: `{occ}`")
    if risk not in (None, "", 0, 0.0):
        try:
            lines.append(f"Risk$: {float(risk):.0f}")
        except (TypeError, ValueError):
            pass
    if skip:
        lines.append(f"Reason: {skip}")
    if status == "failed" and isinstance(broker, dict):
        msg = broker.get("message") or broker.get("error") or ""
        if msg:
            lines.append(f"Broker: {str(msg)[:160]}")

    order_id = str(_g("order_id") or "")
    dedupe = f"{status}:{order_id or sym}:{occ or exp}"
    return post_journal_activity(
        "\n".join(lines),
        title="Mac LIVE auto-trade",
        mention=True,
        dedupe_key=dedupe,
    )


def notify_exit_activity(
    lot: Any,
    *,
    reason: str = "",
    live: bool = True,
    pnl: Optional[float] = None,
) -> Dict[str, Any]:
    """Notify when OMS closes a lot."""
    if not live:
        return {"skipped": True, "reason": "not_live"}

    def _g(key: str, default: Any = "") -> Any:
        if isinstance(lot, dict):
            return lot.get(key, default)
        return getattr(lot, key, default)

    sym = str(_g("symbol") or "?").upper()
    occ = str(_g("occ_symbol") or "")
    qty = _g("quantity") or 1
    lot_id = str(_g("lot_id") or "")
    strategy = str(_g("strategy") or "")[:80]

    lines = [
        f"🔴 **EXIT** **{sym}**",
        f"qty={qty} · reason=`{reason or 'manage'}`",
    ]
    if strategy:
        lines.append(f"Setup: {strategy}")
    if occ:
        lines.append(f"OCC: `{occ}`")
    if pnl is not None:
        sign = "+" if pnl >= 0 else ""
        lines.append(f"Est. P/L: **{sign}${pnl:.2f}**")

    return post_journal_activity(
        "\n".join(lines),
        title="Mac LIVE auto-trade",
        mention=True,
        dedupe_key=f"exit:{lot_id or sym}:{reason}",
    )


def notify_consume_summary(
    *,
    submitted: int,
    failed: int,
    skipped: int,
    cash: Optional[Dict[str, Any]] = None,
    live: bool = True,
) -> Dict[str, Any]:
    """One-line cycle summary when there was action (optional, no per-order spam)."""
    if not live or (submitted <= 0 and failed <= 0):
        return {"skipped": True, "reason": "quiet"}
    # Prefer per-order notifies; summary only if env asks
    if not _env_bool("TRADING_AGENT_JOURNAL_SUMMARY", False):
        return {"skipped": True, "reason": "summary_disabled"}
    bits = [f"submitted={submitted}", f"failed={failed}", f"skipped={skipped}"]
    if cash and cash.get("tradable_after_reserve") is not None:
        bits.append(f"cash≈${cash.get('tradable_after_reserve')}")
    return post_journal_activity(
        " · ".join(bits),
        title="Mac consumer cycle",
        mention=True,
        dedupe_key=f"summary:{datetime.now(PT).strftime('%Y%m%d%H%M')}:{submitted}:{failed}",
    )
