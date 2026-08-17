"""Short Discord ops alerts for Mac auto-trade (fail-open on post errors)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


def _token() -> str:
    return (
        os.getenv("DISCORD_TOKEN", "").strip()
        or os.getenv("DISCORD_BOT_TOKEN", "").strip()
    )


def _channel_id() -> str:
    return (
        os.getenv("DISCORD_OPS_CHANNEL_ID", "").strip()
        or os.getenv("DISCORD_DESK_CHANNEL_ID", "").strip()
        or os.getenv("DISCORD_CHANNEL_ID", "").strip()
        or "1510184298442002502"  # #daily-plays default
    )


def post_ops_alert(
    message: str,
    *,
    title: str = "Auto-trade ops",
    force: bool = False,
) -> List[Dict[str, Any]]:
    """Post a short ops message. Disabled when TRADING_AGENT_OPS_ALERTS=0."""
    flag = os.getenv("TRADING_AGENT_OPS_ALERTS", "1").strip().lower()
    if not force and flag in ("0", "false", "no", "off"):
        return [{"skipped": True, "reason": "ops_alerts_disabled"}]

    token = _token()
    channel = _channel_id()
    if not token or not channel:
        return [{"error": "missing_discord_token_or_channel"}]

    body = f"**{title}**\n{message}".strip()
    if len(body) > 1900:
        body = body[:1890] + "…"

    url = f"https://discord.com/api/v10/channels/{channel}/messages"
    data = json.dumps({"content": body}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "trading-agent-ops/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return [{"ok": True, "status": resp.status, "text": raw[:200]}]
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")[:300]
        return [{"error": f"http_{exc.code}", "detail": err}]
    except Exception as exc:  # noqa: BLE001
        return [{"error": str(exc)}]
