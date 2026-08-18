"""Persist firm run state under sessions/{date}/firm/{symbol}/."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from trading_agent.firm.protocol import FirmCard, FirmMessage
from trading_agent.firm.reports import (
    REPORT_FILENAMES,
    DebateVerdict,
    FundamentalReport,
    ManagerDecision,
    NewsReport,
    RiskAdjustment,
    SentimentReport,
    TechnicalReport,
    TraderProposal,
)
from trading_agent.firm.roles import FIRM_ROLES


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def firm_enabled() -> bool:
    raw = os.getenv("TRADING_AGENT_FIRM", "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def default_session_root() -> Path:
    return Path.home() / ".trading_agent" / "sessions"


def firm_symbol_dir(
    trading_date: str,
    symbol: str,
    *,
    session_root: Optional[Path] = None,
) -> Path:
    root = Path(session_root) if session_root else default_session_root()
    return root / trading_date / "firm" / symbol.upper()


@dataclass
class FirmSymbolState:
    """Global structured state for one symbol on one trading date."""

    symbol: str
    trading_date: str
    schema_version: str = "firm_state_v1"
    status: str = "initialized"  # initialized | running | complete | skipped | error
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    roles: Dict[str, Any] = field(default_factory=dict)
    react_log: List[Dict[str, Any]] = field(default_factory=list)
    messages: List[Dict[str, Any]] = field(default_factory=list)
    card: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    flag_enabled: bool = False

    def touch(self) -> None:
        self.updated_at = _utc_now()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FirmSymbolState":
        from dataclasses import fields as dc_fields

        known = {f.name for f in dc_fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def init_empty_reports(symbol: str, trading_date: str) -> Dict[str, Dict[str, Any]]:
    return {
        "fundamental": FundamentalReport.empty(symbol, trading_date).to_dict(),
        "sentiment": SentimentReport.empty(symbol, trading_date).to_dict(),
        "news": NewsReport.empty(symbol, trading_date).to_dict(),
        "technical": TechnicalReport.empty(symbol, trading_date).to_dict(),
        "debate": DebateVerdict.empty(symbol, trading_date).to_dict(),
        "trader": TraderProposal.empty(symbol, trading_date).to_dict(),
        "risk": RiskAdjustment.empty(symbol, trading_date).to_dict(),
        "manager": ManagerDecision.empty(symbol, trading_date).to_dict(),
    }


def persist_symbol_run(
    state: FirmSymbolState,
    reports: Dict[str, Dict[str, Any]],
    *,
    session_root: Optional[Path] = None,
) -> Path:
    """Write state.json + report files + firm_card.json for one symbol."""
    out_dir = firm_symbol_dir(state.trading_date, state.symbol, session_root=session_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    state.touch()
    write_json(out_dir / "state.json", state.to_dict())
    for key, filename in REPORT_FILENAMES.items():
        if key in reports:
            write_json(out_dir / filename, reports[key])
    card = state.card or FirmCard(
        symbol=state.symbol,
        trading_date=state.trading_date,
        status=state.status,
    ).to_dict()
    write_json(out_dir / "firm_card.json", card)
    # Role contracts snapshot (immutable reference)
    write_json(
        out_dir / "roles.json",
        {name: role.to_dict() for name, role in FIRM_ROLES.items()},
    )
    return out_dir


def load_symbol_state(
    trading_date: str,
    symbol: str,
    *,
    session_root: Optional[Path] = None,
) -> Optional[FirmSymbolState]:
    path = firm_symbol_dir(trading_date, symbol, session_root=session_root) / "state.json"
    data = read_json(path)
    if not data:
        return None
    return FirmSymbolState.from_dict(data)


def append_message(state: FirmSymbolState, message: FirmMessage) -> None:
    state.messages.append(message.to_dict())
    # Cap for disk
    if len(state.messages) > 200:
        state.messages = state.messages[-200:]
    state.touch()
