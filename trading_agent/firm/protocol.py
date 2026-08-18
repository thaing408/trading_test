"""Structured communication protocol (documents as source of truth)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class FirmMessage:
    """Envelope for a persisted firm document or ReAct step."""

    kind: str  # report | debate | proposal | risk | manager | react
    role: str
    symbol: str
    trading_date: str
    payload: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now)
    schema_version: str = "firm_message_v1"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FirmCard:
    """Compact Discord/CIO summary (P7 shape; filled as empty in P0)."""

    symbol: str
    trading_date: str
    fundamental_bullet: str = ""
    sentiment_bullet: str = ""
    news_bullet: str = ""
    technical_bullet: str = ""
    debate_winner: str = "undecided"
    debate_confidence: float = 0.0
    trader_action: str = "HOLD"
    risk_adjustment: str = "unchanged"
    manager_decision: str = "defer"
    status: str = "empty"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_discord_lines(self) -> List[str]:
        return [
            f"**Firm card — {self.symbol}** `{self.trading_date}`",
            f"Fund: {self.fundamental_bullet or '—'}",
            f"Sent: {self.sentiment_bullet or '—'}",
            f"News: {self.news_bullet or '—'}",
            f"Tech: {self.technical_bullet or '—'}",
            f"Debate: **{self.debate_winner}** ({self.debate_confidence:.0f})",
            f"Trader: **{self.trader_action}** · Risk: `{self.risk_adjustment}` · Mgr: `{self.manager_decision}`",
            f"_status={self.status}_",
        ]
