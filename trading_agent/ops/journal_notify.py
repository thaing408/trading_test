"""Post auto-trade activity to Discord #trading-journal with @mention.

Prefer the same path as QQQ scalp:
  ~/.grok/scripts/post-trade-event.sh --json {...}

Falls back to bot API if the script is missing. Config from
~/.grok/discord.env (loaded by consumer):

  DISCORD_BOT_TOKEN / DISCORD_TOKEN
  DISCORD_JOURNAL_CHANNEL_ID   (default #trading-journal)
  DISCORD_JOURNAL_MENTION_USER_ID

Disable: TRADING_AGENT_JOURNAL_ALERTS=0
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")

DEFAULT_JOURNAL_CHANNEL = "1514644765797515426"
DEFAULT_MENTION_USER = "493638750086365194"
JOURNAL_SCRIPT = Path.home() / ".grok" / "scripts" / "post-trade-event.sh"


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


def _post_via_trade_event_script(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Same journal path as QQQ scalp (post-trade-event.sh → @mention journal)."""
    if not JOURNAL_SCRIPT.is_file():
        return {"error": "journal_script_missing", "path": str(JOURNAL_SCRIPT)}
    try:
        proc = subprocess.run(
            [str(JOURNAL_SCRIPT), "--json", json.dumps(payload)],
            check=False,
            timeout=25,
            capture_output=True,
            text=True,
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode == 0:
            if out.startswith("skip duplicate"):
                return {"skipped": True, "reason": "duplicate", "detail": out}
            return {"ok": True, "via": "post-trade-event.sh", "detail": out[:200]}
        return {
            "error": "journal_script_failed",
            "returncode": proc.returncode,
            "stdout": out[:200],
            "stderr": err[:200],
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def notify_order_activity(order: Any, *, live: bool = True) -> Dict[str, Any]:
    """Notify for a ReadyOrder-like object after place (submitted/failed).

    Matches QQQ scalp journal shape: event=entry, symbol=OCC, fill, setup, @mention.
    """
    if not live:
        return {"skipped": True, "reason": "not_live"}
    if not _env_bool("TRADING_AGENT_JOURNAL_ALERTS", True):
        return {"skipped": True, "reason": "journal_alerts_disabled"}

    status = str(getattr(order, "status", "") or "").lower()
    if status not in ("submitted", "failed"):
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
    qty = int(_g("quantity") or 1)
    exp = _g("expiration") or ""
    strikes = _g("strike_prices") or []
    broker = _g("broker_response") or {}
    occ = ""
    if isinstance(broker, dict):
        occ = str(broker.get("occ_symbol") or broker.get("symbol") or "")
    order_id = str(_g("order_id") or "")
    und_px = _g("entry")
    try:
        und_px_f = float(und_px) if und_px not in (None, "") else None
    except (TypeError, ValueError):
        und_px_f = None

    if status == "failed":
        # Failures still go journal so you see rejected places
        msg = ""
        if isinstance(broker, dict):
            msg = str(broker.get("message") or broker.get("error") or "")[:160]
        return post_journal_activity(
            f"⚠️ **ENTRY FAILED** **{sym}** qty={qty}\n"
            f"Setup: {strategy or '—'}\n"
            f"OCC: `{occ or '—'}`\n"
            f"Broker: {msg or _g('skip_reason') or 'failed'}",
            title="Mac LIVE auto-trade",
            mention=True,
            dedupe_key=f"failed:{order_id or sym}:{occ or exp}",
        )

    # submitted — same payload style as QQQ scalp
    payload = {
        "event": "entry",
        "side": "entry",
        "symbol": occ or sym,
        "description": f"{sym} {occ or ''}".strip(),
        "setup": strategy or "multi_method",
        "underlying": sym,
        "qqq_price": und_px_f,  # field name historical; means underlying spot/entry
        "fill_price": None,  # option premium unknown until reconcile
        "quantity": qty,
        "reason": f"Mac multi-method LIVE · strikes={strikes} exp={exp}",
        "order_id": order_id or None,
        "dedupe_key": order_id or f"entry:{sym}:{occ}:{exp}",
        "time_pt": datetime.now(PT).strftime("%Y-%m-%d %H:%M %Z"),
    }
    out = _post_via_trade_event_script(payload)
    if out.get("ok") or out.get("skipped"):
        if payload.get("dedupe_key"):
            _mark_posted(str(payload["dedupe_key"]))
        return out
    # Fallback bot path
    return post_journal_activity(
        f"🟢 **ENTRY** **{sym}** `{occ or '—'}` qty={qty}\nSetup: {strategy or '—'}",
        title="Mac LIVE auto-trade",
        mention=True,
        dedupe_key=str(payload.get("dedupe_key") or ""),
    )


def notify_exit_activity(
    lot: Any,
    *,
    reason: str = "",
    live: bool = True,
    pnl: Optional[float] = None,
    option_mark: Optional[float] = None,
    option_entry: Optional[float] = None,
) -> Dict[str, Any]:
    """Notify when OMS closes a lot — QQQ-style exit journal event."""
    if not live:
        return {"skipped": True, "reason": "not_live"}
    if not _env_bool("TRADING_AGENT_JOURNAL_ALERTS", True):
        return {"skipped": True, "reason": "journal_alerts_disabled"}

    def _g(key: str, default: Any = "") -> Any:
        if isinstance(lot, dict):
            return lot.get(key, default)
        return getattr(lot, key, default)

    sym = str(_g("symbol") or "?").upper()
    occ = str(_g("occ_symbol") or "")
    qty = int(_g("quantity") or 1)
    lot_id = str(_g("lot_id") or "")
    strategy = str(_g("strategy") or "")[:80]
    exit_px = option_mark if option_mark is not None else _g("exit_price")
    entry_opt = option_entry
    if entry_opt is None:
        fe = float(_g("fill_entry") or 0)
        if 0 < fe < 50:
            entry_opt = fe
    if pnl is None and entry_opt is not None and exit_px not in (None, ""):
        try:
            pnl = (float(exit_px) - float(entry_opt)) * qty * 100.0
        except (TypeError, ValueError):
            pnl = None

    payload = {
        "event": "exit",
        "side": "exit",
        "symbol": occ or sym,
        "description": f"{sym} {occ or ''}".strip(),
        "setup": strategy or "multi_method",
        "underlying": sym,
        "fill_price": float(exit_px) if exit_px not in (None, "") else None,
        "entry_price": float(entry_opt) if entry_opt is not None else None,
        "quantity": qty,
        "reason": reason or "manage",
        "order_id": lot_id or None,
        "pnl": round(float(pnl), 2) if pnl is not None else None,
        "dedupe_key": f"exit:{lot_id or sym}:{reason}",
        "time_pt": datetime.now(PT).strftime("%Y-%m-%d %H:%M %Z"),
    }
    out = _post_via_trade_event_script(payload)
    if out.get("ok") or out.get("skipped"):
        if payload.get("dedupe_key"):
            _mark_posted(str(payload["dedupe_key"]))
        return out
    sign = ""
    pnl_s = ""
    if pnl is not None:
        sign = "+" if pnl >= 0 else ""
        pnl_s = f"\nEst. P/L: **{sign}${pnl:.2f}**"
    return post_journal_activity(
        f"🔴 **EXIT** **{sym}** `{occ or '—'}` qty={qty}\nReason: `{reason or 'manage'}`{pnl_s}",
        title="Mac LIVE auto-trade",
        mention=True,
        dedupe_key=str(payload.get("dedupe_key") or ""),
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
