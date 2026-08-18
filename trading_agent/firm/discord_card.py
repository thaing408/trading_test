"""P7 — post compact firm cards to Discord (ops/desk channel)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from trading_agent.firm.protocol import FirmCard


def firm_discord_enabled() -> bool:
    """Opt-in Discord firm cards (default off — set TRADING_AGENT_FIRM_DISCORD=1)."""
    raw = os.getenv("TRADING_AGENT_FIRM_DISCORD", "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def load_firm_card(path: Path) -> Optional[FirmCard]:
    import json

    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not data.get("symbol"):
        return None
    return FirmCard(
        symbol=str(data.get("symbol")),
        trading_date=str(data.get("trading_date") or ""),
        fundamental_bullet=str(data.get("fundamental_bullet") or ""),
        sentiment_bullet=str(data.get("sentiment_bullet") or ""),
        news_bullet=str(data.get("news_bullet") or ""),
        technical_bullet=str(data.get("technical_bullet") or ""),
        debate_winner=str(data.get("debate_winner") or "undecided"),
        debate_confidence=float(data.get("debate_confidence") or 0),
        trader_action=str(data.get("trader_action") or "HOLD"),
        risk_adjustment=str(data.get("risk_adjustment") or "unchanged"),
        manager_decision=str(data.get("manager_decision") or "defer"),
        status=str(data.get("status") or ""),
    )


def format_firm_card_message(card: FirmCard) -> str:
    return "\n".join(card.to_discord_lines())


def post_firm_cards(
    cards: List[FirmCard],
    *,
    title: str = "Firm sleeve",
) -> Dict[str, Any]:
    """Post up to a few firm cards via ops alert channel (fail-open)."""
    if not firm_discord_enabled():
        return {"skipped": True, "reason": "TRADING_AGENT_FIRM_DISCORD=0"}
    if not cards:
        return {"skipped": True, "reason": "no_cards"}
    try:
        from trading_agent.ops.alerts import post_ops_alert
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}

    # Cap message size — first 5 cards
    chunks = []
    for card in cards[:5]:
        chunks.append(format_firm_card_message(card))
    body = "\n\n".join(chunks)
    if len(cards) > 5:
        body += f"\n\n_…+{len(cards) - 5} more symbols_"
    try:
        res = post_ops_alert(body, title=title)
        return {"ok": True, "posted": len(cards[:5]), "result": res}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def post_firm_day(
    trading_date: str,
    *,
    session_root: Optional[Path] = None,
) -> Dict[str, Any]:
    root = Path(session_root) if session_root else Path.home() / ".trading_agent" / "sessions"
    firm_dir = root / trading_date / "firm"
    if not firm_dir.is_dir():
        return {"skipped": True, "reason": "no_firm_dir"}
    cards: List[FirmCard] = []
    for d in sorted(p for p in firm_dir.iterdir() if p.is_dir()):
        card = load_firm_card(d / "firm_card.json")
        if card:
            cards.append(card)
    return post_firm_cards(cards, title=f"Firm sleeve {trading_date}")
