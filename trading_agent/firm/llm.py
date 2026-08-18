"""SpaceXAI / xAI chat helper for firm analysts (OpenAI-compatible).

Env:
  XAI_API_KEY          — required for LLM enrichment
  TRADING_AGENT_FIRM_LLM — 1 (default when firm on) to call LLM; 0 = heuristics only
  TRADING_AGENT_FIRM_LLM_MODEL — default grok-4.5 (deep reports)
  TRADING_AGENT_FIRM_LLM_QUICK_MODEL — default grok-4.5 (or lighter if set)
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


def llm_enabled() -> bool:
    raw = os.getenv("TRADING_AGENT_FIRM_LLM", "1").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    return bool(os.getenv("XAI_API_KEY", "").strip())


def _model(deep: bool = True) -> str:
    if deep:
        return os.getenv("TRADING_AGENT_FIRM_LLM_MODEL", "grok-4.5").strip() or "grok-4.5"
    return (
        os.getenv("TRADING_AGENT_FIRM_LLM_QUICK_MODEL", "").strip()
        or os.getenv("TRADING_AGENT_FIRM_LLM_MODEL", "grok-4.5").strip()
        or "grok-4.5"
    )


def chat_json(
    system: str,
    user: str,
    *,
    deep: bool = True,
    temperature: float = 0.2,
    timeout: int = 60,
) -> Dict[str, Any]:
    """Call xAI chat/completions and parse a JSON object from the reply.

    Returns ``{"ok": True, "data": {...}, "model": ...}`` or
    ``{"ok": False, "error": ..., "raw": ...}``.
    """
    key = os.getenv("XAI_API_KEY", "").strip()
    if not key:
        return {"ok": False, "error": "missing_XAI_API_KEY"}

    model = _model(deep=deep)
    body = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    req = urllib.request.Request(
        "https://api.x.ai/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "trading-agent-firm/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")[:400]
        return {"ok": False, "error": f"http_{exc.code}", "detail": err, "model": model}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "model": model}

    try:
        payload = json.loads(raw)
        text = (
            ((payload.get("choices") or [{}])[0].get("message") or {}).get("content")
            or ""
        )
    except (json.JSONDecodeError, TypeError, IndexError) as exc:
        return {"ok": False, "error": f"bad_response:{exc}", "raw": raw[:500], "model": model}

    data = _extract_json_object(text)
    if data is None:
        return {"ok": False, "error": "no_json_in_reply", "raw": text[:800], "model": model}
    return {"ok": True, "data": data, "model": model, "raw_text": text[:500]}


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    text = (text or "").strip()
    if not text:
        return None
    # fenced ```json
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(1))
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            pass
    # raw object
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None
