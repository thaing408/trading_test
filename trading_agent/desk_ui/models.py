"""DeskSnapshot DTOs for desk_ui v1."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from trading_agent.desk_ui.market_context import MarketContext
from trading_agent.desk_ui.phase import PhaseStatus

RejectionSource = Literal["plan", "book_incomplete"]
HostRole = Literal["windows-research", "mac-execute", "unknown"]


@dataclass
class RejectionRow:
    symbol: str
    reason: str
    source: RejectionSource
    gates: list[str] = field(default_factory=list)


@dataclass
class ExportPathHealth:
    path: str
    exists: bool
    mtime_iso: str | None
    age_seconds: float | None


@dataclass
class ExportHealth:
    targets: list[ExportPathHealth]
    trading_date_match: bool
    wrong_day: bool
    last_write_age_seconds: float | None
    stale_missed_slot: bool
    stale_suppressed_cash: bool
    notes: list[str] = field(default_factory=list)


@dataclass
class ManageView:
    paths_read: list[str]
    summary: dict[str, Any]
    latest_cycle: dict[str, Any] | None
    recent: list[dict[str, Any]]  # newest first
    quiet: bool
    quiet_reason: str


@dataclass
class PositionsView:
    available: bool
    path: str | None
    positions: list[dict[str, Any]]
    empty_reason: str


@dataclass
class DeskSnapshot:
    trading_date: str
    host: str
    host_role: HostRole
    book_role: str
    phase: PhaseStatus
    stay_in_cash: bool
    cash_reason: str
    environment_score: float | None
    regime: str
    book_raw: dict[str, Any]
    scanned_raw: dict[str, Any]
    entries: list[dict[str, Any]]
    watchlist: list[str]
    play_symbols: list[str]
    rejections: list[RejectionRow]
    export_health: ExportHealth
    manage: ManageView
    positions: PositionsView
    oms_lots: list[dict[str, Any]]
    kill_switch: dict[str, Any]
    process_cards: list[dict[str, Any]]
    gap_book_summary: dict[str, Any] | None
    operator_flags: dict[str, Any]
    acknowledgements: dict[str, Any]
    broker_boundary: str
    generated_at: str
    market: MarketContext = field(default_factory=MarketContext)
    platform: str = ""
    parse_failures: int = 0
    panel_errors: dict[str, str] = field(default_factory=dict)
    # Execute-side (Mac) + firm sleeve panels
    account_cash: dict[str, Any] = field(default_factory=dict)
    ready_orders: dict[str, Any] = field(default_factory=dict)
    consumer_health: dict[str, Any] = field(default_factory=dict)
    oms_summary: dict[str, Any] = field(default_factory=dict)
    firm: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable dict (datetimes → iso)."""

        def _convert(obj: Any) -> Any:
            if hasattr(obj, "isoformat") and callable(obj.isoformat):
                try:
                    return obj.isoformat()
                except Exception:
                    return str(obj)
            if isinstance(obj, dict):
                return {k: _convert(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_convert(v) for v in obj]
            return obj

        return _convert(asdict(self))
