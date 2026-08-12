"""Durable OMS state: processed fingerprints, open lots, order lifecycle."""

from __future__ import annotations

import json
import os
import socket
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from trading_agent.oms.audit import default_oms_dir


class LotStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    OPEN = "open"
    PROTECTED = "protected"
    EXITING = "exiting"
    CLOSED = "closed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class OpenLot:
    lot_id: str
    fingerprint: str
    symbol: str
    instrument: str
    strategy: str
    setup_id: str
    side: str
    quantity: int
    entry: float
    stop: float
    target: float
    max_risk_dollars: float
    status: str = LotStatus.PENDING.value
    occ_symbol: str = ""
    strike_prices: List[float] = field(default_factory=list)
    expiration: str = ""
    place_path: str = ""
    broker_order_id: str = ""
    submitted_at: str = ""
    opened_at: str = ""
    closed_at: str = ""
    exit_reason: str = ""
    exit_price: float = 0.0
    expected_entry: float = 0.0
    fill_entry: float = 0.0
    slippage: float = 0.0
    source_book: str = ""
    notes: str = ""
    broker_meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OpenLot":
        from dataclasses import fields as dc_fields

        known = {f.name for f in dc_fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


class OmsStore:
    """JSON-backed OMS store under ~/.trading_agent/oms/."""

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root else default_oms_dir()
        self.state_path = self.root / "state.json"
        self._data: Dict[str, Any] = {
            "schema_version": 1,
            "host": socket.gethostname(),
            "updated_at": "",
            "processed_ids": [],
            "lots": {},
            "day_realized_pnl": 0.0,
            "day_key": "",
            # Closed round-trips today by symbol (reset each ensure_day)
            "day_round_trips": {},
        }
        self.load()

    def load(self) -> None:
        try:
            if self.state_path.is_file():
                raw = json.loads(self.state_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._data.update(raw)
                    if not isinstance(self._data.get("lots"), dict):
                        self._data["lots"] = {}
                    if not isinstance(self._data.get("processed_ids"), list):
                        self._data["processed_ids"] = []
        except (OSError, json.JSONDecodeError):
            pass

    def save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._data["host"] = socket.gethostname()
        # cap processed list
        ids = list(self._data.get("processed_ids") or [])
        self._data["processed_ids"] = ids[-2000:]
        self.state_path.write_text(json.dumps(self._data, indent=2, default=str) + "\n", encoding="utf-8")

    def processed_ids(self) -> set[str]:
        return set(self._data.get("processed_ids") or [])

    def mark_processed(self, fingerprint: str) -> None:
        ids = list(self._data.get("processed_ids") or [])
        if fingerprint not in ids:
            ids.append(fingerprint)
        self._data["processed_ids"] = ids

    def is_processed(self, fingerprint: str) -> bool:
        return fingerprint in self.processed_ids()

    def upsert_lot(self, lot: OpenLot) -> None:
        lots = self._data.setdefault("lots", {})
        lots[lot.lot_id] = lot.to_dict()

    def get_lot(self, lot_id: str) -> Optional[OpenLot]:
        raw = (self._data.get("lots") or {}).get(lot_id)
        if not raw:
            return None
        return OpenLot.from_dict(raw)

    def open_lots(self) -> List[OpenLot]:
        out: List[OpenLot] = []
        for raw in (self._data.get("lots") or {}).values():
            if not isinstance(raw, dict):
                continue
            st = str(raw.get("status") or "")
            if st in (
                LotStatus.SUBMITTED.value,
                LotStatus.OPEN.value,
                LotStatus.PROTECTED.value,
                LotStatus.EXITING.value,
                LotStatus.PENDING.value,
            ):
                out.append(OpenLot.from_dict(raw))
        return out

    def all_lots(self) -> List[OpenLot]:
        return [
            OpenLot.from_dict(raw)
            for raw in (self._data.get("lots") or {}).values()
            if isinstance(raw, dict)
        ]

    def ensure_day(self, day_key: str) -> None:
        if self._data.get("day_key") != day_key:
            self._data["day_key"] = day_key
            self._data["day_realized_pnl"] = 0.0
            self._data["day_round_trips"] = {}

    def add_realized_pnl(self, pnl: float) -> None:
        self._data["day_realized_pnl"] = float(self._data.get("day_realized_pnl") or 0.0) + float(pnl)

    def day_realized_pnl(self) -> float:
        return float(self._data.get("day_realized_pnl") or 0.0)

    def day_round_trips_map(self) -> Dict[str, int]:
        raw = self._data.get("day_round_trips") or {}
        if not isinstance(raw, dict):
            return {}
        out: Dict[str, int] = {}
        for k, v in raw.items():
            try:
                out[str(k).upper()] = int(v)
            except (TypeError, ValueError):
                continue
        return out

    def symbol_round_trips_today(self, symbol: str) -> int:
        """Closed round-trips for symbol today (+ closed lots not yet recorded)."""
        sym = str(symbol or "").upper().strip()
        if not sym:
            return 0
        counted = int(self.day_round_trips_map().get(sym, 0) or 0)
        # Also count CLOSED lots closed on this day_key (idempotent upper bound)
        day = str(self._data.get("day_key") or "")
        closed_n = 0
        for lot in self.all_lots():
            if lot.symbol.upper() != sym:
                continue
            if lot.status != LotStatus.CLOSED.value:
                continue
            closed_at = str(lot.closed_at or "")
            if day and closed_at.startswith(day):
                closed_n += 1
            elif not day and closed_at:
                closed_n += 1
        return max(counted, closed_n)

    def total_round_trips_today(self) -> int:
        return int(sum(self.day_round_trips_map().values()))

    def record_round_trip(self, symbol: str) -> int:
        """Increment closed round-trip count for symbol; return new count."""
        sym = str(symbol or "").upper().strip()
        if not sym:
            return 0
        m = self.day_round_trips_map()
        m[sym] = int(m.get(sym, 0) or 0) + 1
        self._data["day_round_trips"] = m
        return m[sym]

    def open_risk_dollars(self) -> float:
        total = 0.0
        for lot in self.open_lots():
            total += max(0.0, float(lot.max_risk_dollars or 0.0))
        return total

    def open_count(self) -> int:
        return len(self.open_lots())
