"""Schwab OAuth token health for Mac LIVE preflight."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict


def schwab_oauth_status() -> Dict[str, Any]:
    """Return status of Schwab refresh token age (7-day window).

    Keys: ok, status (OK|REAUTH_SOON|NEED_OAUTH|NO_TOKEN), age_days, remaining_days,
    token_path, message.
    """
    token_path = Path(
        os.getenv("SCHWAB_TOKEN_PATH", str(Path.home() / ".schwab-mcp" / "token.json"))
    ).expanduser()
    state_path = Path.home() / ".grok" / "state" / "schwab-oauth.json"
    now = time.time()
    out: Dict[str, Any] = {
        "ok": False,
        "status": "NO_TOKEN",
        "age_days": None,
        "remaining_days": None,
        "token_path": str(token_path),
        "message": "",
    }
    if not token_path.is_file():
        out["message"] = f"No token file: {token_path}"
        return out
    try:
        data = json.loads(token_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        out["message"] = f"token unreadable: {exc}"
        return out

    oauth_at = data.get("oauth_at") or data.get("refresh_issued_at")
    if oauth_at is None and state_path.is_file():
        try:
            oauth_at = json.loads(state_path.read_text(encoding="utf-8")).get("last_oauth_at")
        except (OSError, json.JSONDecodeError):
            oauth_at = None
    if oauth_at is None:
        oauth_at = token_path.stat().st_mtime
        source = "mtime"
    else:
        source = "oauth_at"

    age_days = (now - float(oauth_at)) / 86400.0
    remaining = 7.0 - age_days
    out["age_days"] = round(age_days, 2)
    out["remaining_days"] = round(remaining, 2)
    out["source"] = source

    if remaining <= 0:
        out["status"] = "NEED_OAUTH"
        out["message"] = f"Schwab refresh expired ~{-remaining:.1f}d ago — run schwab-oauth.sh"
        out["ok"] = False
    elif remaining <= 1.0:
        out["status"] = "REAUTH_SOON"
        out["message"] = f"Schwab re-auth soon (~{remaining:.1f}d left)"
        out["ok"] = True  # still usable
    else:
        out["status"] = "OK"
        out["message"] = f"Schwab OAuth OK (~{remaining:.1f}d left)"
        out["ok"] = True
    return out


def schwab_live_blocked_reason() -> str:
    """Empty if LIVE ok; else short reason to block place attempts."""
    if os.getenv("TRADING_AGENT_SCHWAB_HEALTH_CHECK", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return ""
    st = schwab_oauth_status()
    if st.get("status") == "NO_TOKEN":
        return "schwab_no_token"
    if st.get("status") == "NEED_OAUTH":
        return "schwab_oauth_expired"
    return ""
