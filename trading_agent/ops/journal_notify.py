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


def _schwab_order_id(broker: Any) -> str:
    """Extract Schwab order id from place_order response (same as QQQ scalp)."""
    if not isinstance(broker, dict):
        return ""
    for key in ("order_id", "orderId", "broker_order_id"):
        v = broker.get(key)
        if v:
            return str(v)
    loc = ""
    resp = broker.get("response")
    if isinstance(resp, dict):
        loc = str(resp.get("location") or "")
        for key in ("order_id", "orderId"):
            if resp.get(key):
                return str(resp[key])
    if not loc:
        loc = str(broker.get("location") or "")
    if "/orders/" in loc:
        return loc.rsplit("/orders/", 1)[-1].strip()
    return ""


def _as_opt_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _order_get(order: Any, key: str, default: Any = "") -> Any:
    if isinstance(order, dict):
        return order.get(key, default)
    return getattr(order, key, default)


def _setup_label(order: Any) -> str:
    setup_id = str(_order_get(order, "setup_id") or "").strip()
    strategy = str(_order_get(order, "strategy") or "").strip()
    setup = setup_id or strategy or "multi_method"
    if setup.lower().startswith("multi-method"):
        setup = setup_id or "multi_method"
    return setup


# Ops skip reasons worth a Discord ping (day+symbol deduped).
SKIP_ALERT_REASONS = frozenset(
    {
        "before_rth_open",
        "after_entry_window",
        "max_open_risk",
        "max_open_lots",
        "insufficient_buying_power",
        "account_cash_unavailable",
        "schwab_oauth_expired",
        "schwab_no_token",
        "insufficient_debit_cash",
        "insufficient_credit_bp",
        "missing_account_balances",
        "credit_undefined_risk",
    }
)


def skip_reason_should_alert(reason: str) -> bool:
    r = (reason or "").strip()
    if not r:
        return False
    if r in SKIP_ALERT_REASONS:
        return True
    if r.startswith("insufficient_cash") or r.startswith("insufficient_margin"):
        return True
    if r.startswith("afford") or r.startswith("credit_"):
        return True
    if r.startswith("schwab_"):
        return True
    if r.startswith("before_rth") or r.startswith("after_entry"):
        return True
    if r.startswith("max_open"):
        return True
    return False


def _human_skip_reason(reason: str, order: Any = None) -> str:
    r = (reason or "").strip()
    broker = {}
    if order is not None:
        br = _order_get(order, "broker_response") or {}
        if isinstance(br, dict):
            broker = br
    msg = str(broker.get("message") or "").strip()
    labels = {
        "before_rth_open": "Held until RTH open (09:30 ET) — will retry after open",
        "after_entry_window": "Past entry window — no new LIVE entries",
        "max_open_risk": "Blocked: max open risk",
        "max_open_lots": "Blocked: max open lots",
        "insufficient_buying_power": "Blocked: insufficient buying power",
        "account_cash_unavailable": "Blocked: account cash/BP unavailable",
        "schwab_oauth_expired": "Blocked: Schwab OAuth expired — refresh token",
        "schwab_no_token": "Blocked: no Schwab token",
        "insufficient_debit_cash": "Blocked: cash cannot fund debit premium",
        "insufficient_credit_bp": "Blocked: BP cannot fund credit/short premium",
        "missing_account_balances": "Blocked: missing account balances",
        "credit_undefined_risk": "Blocked: credit package missing defined risk",
    }
    if r in labels:
        base = labels[r]
    elif r.startswith("insufficient_cash"):
        base = f"Blocked: insufficient cash ({r})"
    else:
        base = f"Skipped: {r}"
    if msg and msg.lower() not in base.lower():
        return f"{base} — {msg[:120]}"
    return base


def notify_skip_activity(
    order: Any,
    *,
    reason: str = "",
    live: bool = True,
) -> Dict[str, Any]:
    """Discord ops alert when LIVE place is skipped (RTH / cash / risk).

    Day+symbol+reason dedupe so consumer polls do not spam.
    Disable: TRADING_AGENT_JOURNAL_SKIP_ALERTS=0
    """
    if not live:
        return {"skipped": True, "reason": "not_live"}
    if not _env_bool("TRADING_AGENT_JOURNAL_ALERTS", True):
        return {"skipped": True, "reason": "journal_alerts_disabled"}
    if not _env_bool("TRADING_AGENT_JOURNAL_SKIP_ALERTS", True):
        return {"skipped": True, "reason": "skip_alerts_disabled"}

    skip = (reason or str(_order_get(order, "skip_reason") or "")).strip()
    if not skip_reason_should_alert(skip):
        return {"skipped": True, "reason": f"skip_not_alertable:{skip or 'empty'}"}

    sym = str(_order_get(order, "symbol") or "?").upper()
    setup = _setup_label(order)
    day = datetime.now(PT).strftime("%Y-%m-%d")
    text = _human_skip_reason(skip, order)
    broker = _order_get(order, "broker_response") or {}
    extra = ""
    if isinstance(broker, dict):
        need = broker.get("cash_required")
        have = broker.get("remaining_cash")
        aff = broker.get("affordability") if isinstance(broker.get("affordability"), dict) else {}
        if need is not None or have is not None:
            extra = f"\nCash need/have: `{need}` / `{have}`"
        elif aff:
            extra = f"\nNeed/have: `{aff.get('need')}` / `{aff.get('have')}` ({aff.get('kind') or ''})"

    return post_journal_activity(
        f"⏸️ **MULTI AUTO — ENTRY SKIPPED**\n"
        f"**{sym}** · Setup: **{setup}**\n"
        f"{text}{extra}",
        title="Mac LIVE auto-trade",
        mention=True,
        dedupe_key=f"skip:{day}:{sym}:{skip.split(':')[0]}",
    )


def notify_working_activity(
    order: Any,
    *,
    live: bool = True,
) -> Dict[str, Any]:
    """Quiet note that order was accepted but fill not yet confirmed.

    No @mention by default. Disable: TRADING_AGENT_JOURNAL_WORKING_ALERTS=0
    """
    if not live:
        return {"skipped": True, "reason": "not_live"}
    if not _env_bool("TRADING_AGENT_JOURNAL_ALERTS", True):
        return {"skipped": True, "reason": "journal_alerts_disabled"}
    if not _env_bool("TRADING_AGENT_JOURNAL_WORKING_ALERTS", True):
        return {"skipped": True, "reason": "working_alerts_disabled"}

    sym = str(_order_get(order, "symbol") or "?").upper()
    setup = _setup_label(order)
    broker = _order_get(order, "broker_response") or {}
    if not isinstance(broker, dict):
        broker = {}
    occ = str(broker.get("occ_symbol") or "").strip()
    oid = _schwab_order_id(broker) or str(_order_get(order, "order_id") or "")
    day = datetime.now(PT).strftime("%Y-%m-%d")
    return post_journal_activity(
        f"⏳ **MULTI AUTO — WORKING** (fill not confirmed yet)\n"
        f"**{sym} {occ}**\n"
        f"Setup: **{setup}**\n"
        f"Will post 🟢 ENTRY when position is at the broker."
        + (f"\nOrder: `{oid}`" if oid else ""),
        title="Mac LIVE auto-trade",
        mention=False,
        dedupe_key=f"working:{day}:{oid or sym}:{occ}",
    )


def notify_lot_entry_filled(
    lot: Any,
    *,
    live: bool = True,
    fill_price: Optional[float] = None,
    spot_price: Optional[float] = None,
) -> Dict[str, Any]:
    """Green ENTER from OMS lot after position reconcile confirmed the fill."""
    if not live:
        return {"skipped": True, "reason": "not_live"}
    if not _env_bool("TRADING_AGENT_JOURNAL_ALERTS", True):
        return {"skipped": True, "reason": "journal_alerts_disabled"}

    def _g(key: str, default: Any = "") -> Any:
        if isinstance(lot, dict):
            return lot.get(key, default)
        return getattr(lot, key, default)

    sym = str(_g("symbol") or "?").upper()
    occ = str(_g("occ_symbol") or "").strip()
    qty = int(_g("quantity") or 1)
    setup = str(_g("setup_id") or "").strip() or str(_g("strategy") or "").strip() or "multi_method"
    if setup.lower().startswith("multi-method"):
        setup = str(_g("setup_id") or "multi_method")
    lot_id = str(_g("lot_id") or "")
    oid = str(_g("broker_order_id") or lot_id)
    meta = _g("broker_meta") or {}
    if not isinstance(meta, dict):
        meta = {}
    fill_f = fill_price
    if fill_f is None:
        fill_f = _as_opt_float(meta.get("option_entry_premium"))
    if fill_f is None:
        fe = _as_opt_float(_g("fill_entry"))
        if fe is not None and 0 < fe < 50:
            fill_f = fe
    und_px_f = spot_price if spot_price is not None else _as_opt_float(_g("entry"))
    exp = _g("expiration") or ""
    reason = (
        f"{sym} fill confirmed at broker · {setup}"
        + (f" · exp {exp}" if exp else "")
    )
    payload = {
        "event": "entry",
        "side": "entry",
        "label": "MULTI AUTO",
        "symbol": occ or sym,
        "description": f"{sym} {occ}".strip() if occ else sym,
        "setup": setup,
        "underlying": sym,
        "qqq_price": und_px_f,
        "fill_price": fill_f,
        "quantity": qty,
        "reason": reason,
        "order_id": oid or None,
        "dedupe_key": f"entry:{oid or lot_id or sym}:{occ or exp}",
        "time_pt": datetime.now(PT).strftime("%Y-%m-%d %H:%M %Z"),
    }
    out = _post_via_trade_event_script(payload)
    if out.get("ok") or out.get("skipped"):
        if payload.get("dedupe_key"):
            _mark_posted(str(payload["dedupe_key"]))
        return out
    lines = [
        "🟢 **MULTI AUTO — ENTRY**",
        f"**{payload['description']}**",
        f"`{payload['time_pt']}`",
        f"Setup: **{setup}**",
        f"Underlying: **{sym}**",
    ]
    if und_px_f is not None:
        lines.append(f"Spot: **${und_px_f:.2f}**")
    if fill_f is not None:
        lines.append(f"Fill: **${fill_f:.2f}** × {qty}")
    lines.append(f"Reason: {reason}")
    if oid:
        lines.append(f"Order: `{oid}`")
    return post_journal_activity(
        "\n".join(lines),
        title="Mac LIVE auto-trade",
        mention=True,
        dedupe_key=str(payload.get("dedupe_key") or ""),
    )


def notify_order_activity(
    order: Any,
    *,
    live: bool = True,
    fill_price: Optional[float] = None,
    spot_price: Optional[float] = None,
    fill_confirmed: Optional[bool] = None,
) -> Dict[str, Any]:
    """Notify for a ReadyOrder-like object after place (submitted/failed).

    Green 🟢 ENTRY only when ``fill_confirmed`` is True (broker filled status
    or position reconcile). Mere place-accept posts ⏳ WORKING instead.

    Matches QQQ scalp #trading-journal format exactly via post-trade-event.sh:

      @Thai
      🟢 MULTI AUTO — ENTRY
      AMD AMD   260821C00515000
      2026-08-17 09:08 PDT
      Setup: multi_swing_daily
      Underlying: AMD
      Spot: $511.46
      Fill: $3.40 × 1
      Reason: ...
      Order: 1007566550639
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
        return _order_get(order, key, default)

    sym = str(_g("symbol") or "?").upper()
    setup = _setup_label(order)
    qty = int(_g("quantity") or 1)
    exp = _g("expiration") or ""
    strikes = _g("strike_prices") or []
    notes = str(_g("notes") or "")[:200]
    broker = _g("broker_response") or {}
    if not isinstance(broker, dict):
        broker = {}
    occ = str(broker.get("occ_symbol") or broker.get("symbol") or "").strip()
    fingerprint = str(_g("order_id") or "")
    schwab_oid = _schwab_order_id(broker) or fingerprint

    # Spot: live override → structure entry
    und_px_f = spot_price if spot_price is not None else _as_opt_float(_g("entry"))

    # Fill: explicit premium → broker meta → none
    fill_f = fill_price
    if fill_f is None:
        fill_f = _as_opt_float(broker.get("option_entry_premium"))
    if fill_f is None:
        fill_f = _as_opt_float(broker.get("fill_price"))

    if status == "failed":
        msg = str(broker.get("message") or broker.get("error") or _g("skip_reason") or "failed")[:160]
        return post_journal_activity(
            f"⚠️ **MULTI AUTO — ENTRY FAILED**\n"
            f"**{sym} {occ or ''}**\n"
            f"Setup: **{setup}**\n"
            f"Broker: {msg}",
            title="Mac LIVE auto-trade",
            mention=True,
            dedupe_key=f"failed:{schwab_oid or sym}:{occ or exp}",
        )

    # Gate green ENTER on confirmed fill (default: infer from broker status)
    if fill_confirmed is None:
        try:
            from trading_agent.oms.lifecycle import broker_status_is_filled

            fill_confirmed = broker_status_is_filled(broker)
        except Exception:  # noqa: BLE001
            fill_confirmed = False
    if not fill_confirmed:
        return notify_working_activity(order, live=True)

    # Reason line — mirror QQQ prose style
    strike_s = ""
    if strikes:
        try:
            strike_s = ",".join(str(float(s)) for s in strikes[:3])
        except (TypeError, ValueError):
            strike_s = str(strikes)
    reason = notes or (
        f"{sym} multi-method LIVE · {setup}"
        + (f" · strike {strike_s}" if strike_s else "")
        + (f" · exp {exp}" if exp else "")
    )

    # Exact same payload keys QQQ scalp uses → same Discord layout
    payload = {
        "event": "entry",
        "side": "entry",
        "label": "MULTI AUTO",
        "symbol": occ or sym,
        "description": f"{sym} {occ}".strip() if occ else sym,
        "setup": setup,
        "underlying": sym,
        "qqq_price": und_px_f,  # rendered as Spot: $X.XX
        "fill_price": fill_f,  # rendered as Fill: $X.XX × qty
        "quantity": qty,
        "reason": reason,
        "order_id": schwab_oid or None,
        "dedupe_key": schwab_oid or f"entry:{sym}:{occ}:{exp}",
        "time_pt": datetime.now(PT).strftime("%Y-%m-%d %H:%M %Z"),
    }
    out = _post_via_trade_event_script(payload)
    if out.get("ok") or out.get("skipped"):
        if payload.get("dedupe_key"):
            _mark_posted(str(payload["dedupe_key"]))
        return out
    # Fallback — still mirror QQQ line layout
    lines = [
        "🟢 **MULTI AUTO — ENTRY**",
        f"**{payload['description']}**",
        f"`{payload['time_pt']}`",
        f"Setup: **{setup}**",
        f"Underlying: **{sym}**",
    ]
    if und_px_f is not None:
        lines.append(f"Spot: **${und_px_f:.2f}**")
    if fill_f is not None:
        lines.append(f"Fill: **${fill_f:.2f}** × {qty}")
    lines.append(f"Reason: {reason}")
    if schwab_oid:
        lines.append(f"Order: `{schwab_oid}`")
    return post_journal_activity(
        "\n".join(lines),
        title="Mac LIVE auto-trade",
        mention=True,
        dedupe_key=str(payload.get("dedupe_key") or ""),
    )


def _format_exit_reason(
    *,
    raw_reason: str,
    entry_opt: Optional[float],
    exit_opt: Optional[float],
    profit_pct_limit: float = 100.0,
    loss_pct_limit: float = 50.0,
) -> str:
    """QQQ-style reason: HARD TARGET +37.7% on option bid (entry $0.61 → $0.84, limit +25%)."""
    reason = (raw_reason or "manage").strip()
    pnl_pct: Optional[float] = None
    if entry_opt and exit_opt and entry_opt > 0:
        pnl_pct = (exit_opt - entry_opt) / entry_opt * 100.0

    # Map internal manage reasons → QQQ phrasing
    low = reason.lower()
    if pnl_pct is not None and (
        "option_target" in low or reason.startswith("option_target")
    ):
        return (
            f"HARD TARGET {pnl_pct:+.1f}% on option mark "
            f"(entry ${entry_opt:.2f} → ${exit_opt:.2f}, limit +{profit_pct_limit:.0f}%)"
        )
    if pnl_pct is not None and (
        "option_stop" in low or reason.startswith("option_stop")
    ):
        return (
            f"HARD STOP {pnl_pct:+.1f}% on option mark "
            f"(entry ${entry_opt:.2f} → ${exit_opt:.2f}, limit -{loss_pct_limit:.0f}%)"
        )
    if reason in ("profit_target", "stop_loss", "range_high_break", "range_low_break"):
        label = {
            "profit_target": "UNDERLYING TARGET",
            "stop_loss": "UNDERLYING STOP",
            "range_high_break": "RANGE HIGH BREAK",
            "range_low_break": "RANGE LOW BREAK",
        }.get(reason, reason.upper())
        if entry_opt is not None and exit_opt is not None and pnl_pct is not None:
            return (
                f"{label} — option {pnl_pct:+.1f}% "
                f"(entry ${entry_opt:.2f} → ${exit_opt:.2f})"
            )
        return label
    if reason.startswith("eod_0dte") or reason == "expired_option_flatten":
        base = "EOD 0DTE FLATTEN" if "eod" in low else "EXPIRED OPTION FLATTEN"
        if entry_opt is not None and exit_opt is not None and pnl_pct is not None:
            return f"{base} — option {pnl_pct:+.1f}% (entry ${entry_opt:.2f} → ${exit_opt:.2f})"
        return base
    if reason.startswith("min_premium_wipe"):
        if entry_opt is not None and exit_opt is not None:
            return (
                f"MIN PREMIUM WIPE — mark ${exit_opt:.3f} "
                f"(entry ${entry_opt:.2f})"
            )
        return f"MIN PREMIUM WIPE — {reason}"
    if entry_opt is not None and exit_opt is not None and pnl_pct is not None:
        return f"{reason} — option {pnl_pct:+.1f}% (entry ${entry_opt:.2f} → ${exit_opt:.2f})"
    return reason


def notify_exit_activity(
    lot: Any,
    *,
    reason: str = "",
    live: bool = True,
    pnl: Optional[float] = None,
    option_mark: Optional[float] = None,
    option_entry: Optional[float] = None,
    spot_price: Optional[float] = None,
    order_id: str = "",
) -> Dict[str, Any]:
    """Notify when OMS closes a lot — same #trading-journal layout as QQQ EXIT.

      @Thai
      🔴 MULTI AUTO — EXIT
      QQQ QQQ   260812C00725000
      2026-08-12 09:49 PDT
      Setup: bull_breakout
      Underlying: QQQ
      Spot: $724.79
      Fill: $0.82 × 1
      Est. P/L: +$21.50
      Reason: HARD TARGET +37.7% on option bid (entry $0.61 → $0.84, limit +25%)
      Order: 1007567425260
    """
    if not live:
        return {"skipped": True, "reason": "not_live"}
    if not _env_bool("TRADING_AGENT_JOURNAL_ALERTS", True):
        return {"skipped": True, "reason": "journal_alerts_disabled"}

    def _g(key: str, default: Any = "") -> Any:
        if isinstance(lot, dict):
            return lot.get(key, default)
        return getattr(lot, key, default)

    sym = str(_g("symbol") or "?").upper()
    occ = str(_g("occ_symbol") or "").strip()
    qty = int(_g("quantity") or 1)
    lot_id = str(_g("lot_id") or "")
    setup_id = str(_g("setup_id") or "").strip()
    strategy = str(_g("strategy") or "").strip()
    setup = setup_id or strategy or "multi_method"

    # Option premiums
    exit_opt = option_mark
    if exit_opt is None:
        exit_opt = _as_opt_float(_g("exit_price"))
        if exit_opt is not None and exit_opt >= 50:
            exit_opt = None  # underlying, not premium
    entry_opt = option_entry
    if entry_opt is None:
        meta = _g("broker_meta") or {}
        if isinstance(meta, dict):
            for key in ("option_entry_premium", "entry_option_price", "option_mark_at_entry"):
                entry_opt = _as_opt_float(meta.get(key))
                if entry_opt is not None:
                    break
    if entry_opt is None:
        fe = _as_opt_float(_g("fill_entry"))
        if fe is not None and 0 < fe < 50:
            entry_opt = fe

    if pnl is None and entry_opt is not None and exit_opt is not None:
        pnl = (float(exit_opt) - float(entry_opt)) * qty * 100.0

    try:
        loss_lim = float(os.getenv("TRADING_AGENT_OPTION_LOSS_PCT", "50") or 50)
    except ValueError:
        loss_lim = 50.0
    try:
        profit_lim = float(os.getenv("TRADING_AGENT_OPTION_PROFIT_PCT", "100") or 100)
    except ValueError:
        profit_lim = 100.0

    reason_text = _format_exit_reason(
        raw_reason=reason or str(_g("exit_reason") or "manage"),
        entry_opt=entry_opt,
        exit_opt=exit_opt,
        profit_pct_limit=profit_lim,
        loss_pct_limit=loss_lim,
    )

    # Close order id from broker close response if present
    schwab_oid = (order_id or "").strip()
    if not schwab_oid:
        meta = _g("broker_meta") or {}
        if isinstance(meta, dict):
            close = meta.get("close") or {}
            if isinstance(close, dict):
                schwab_oid = _schwab_order_id(close) or _schwab_order_id(
                    close.get("response") if isinstance(close.get("response"), dict) else {}
                )
            if not schwab_oid:
                schwab_oid = _schwab_order_id(meta.get("broker_response") or {})
    if not schwab_oid:
        schwab_oid = lot_id

    spot = spot_price
    if spot is None:
        # underlying structure entry is better than nothing for Spot line
        und_entry = _as_opt_float(_g("entry"))
        if und_entry is not None and und_entry >= 50:
            spot = und_entry

    payload = {
        "event": "exit",
        "side": "exit",
        "label": "MULTI AUTO",
        "symbol": occ or sym,
        "description": f"{sym} {occ}".strip() if occ else sym,
        "setup": setup,
        "underlying": sym,
        "qqq_price": spot,  # Spot: $X.XX
        "fill_price": float(exit_opt) if exit_opt is not None else None,  # Fill exit premium
        # Do not set entry_price — QQQ embeds entry→exit in Reason (no separate Entry line)
        "quantity": qty,
        "reason": reason_text,
        "order_id": schwab_oid or None,
        "pnl": round(float(pnl), 2) if pnl is not None else None,
        "dedupe_key": f"exit:{lot_id or sym}:{reason or 'manage'}",
        "time_pt": datetime.now(PT).strftime("%Y-%m-%d %H:%M %Z"),
    }
    out = _post_via_trade_event_script(payload)
    if out.get("ok") or out.get("skipped"):
        if payload.get("dedupe_key"):
            _mark_posted(str(payload["dedupe_key"]))
        return out

    lines = [
        "🔴 **MULTI AUTO — EXIT**",
        f"**{payload['description']}**",
        f"`{payload['time_pt']}`",
        f"Setup: **{setup}**",
        f"Underlying: **{sym}**",
    ]
    if spot is not None:
        lines.append(f"Spot: **${float(spot):.2f}**")
    if exit_opt is not None:
        lines.append(f"Fill: **${float(exit_opt):.2f}** × {qty}")
    if pnl is not None:
        sign = "+" if pnl >= 0 else ""
        lines.append(f"Est. P/L: **{sign}${float(pnl):.2f}**")
    lines.append(f"Reason: {reason_text}")
    if schwab_oid:
        lines.append(f"Order: `{schwab_oid}`")
    return post_journal_activity(
        "\n".join(lines),
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
