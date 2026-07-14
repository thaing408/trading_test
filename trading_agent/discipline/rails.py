"""Discipline rails: max concurrent risk / plays and post-stop cool-down (no revenge).

Douglas process + Steenbarger habit: predefined risk limits; do not re-enter
the same symbol after a session stop-out within the cool-down window.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Mapping, Optional, Sequence


def _parse_ts(value: str | datetime | None) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


@dataclass
class SessionRiskState:
    """Mutable session book for cool-down and concurrent risk."""

    open_symbols: List[str] = field(default_factory=list)
    open_risk_pct: float = 0.0
    stop_outs: List[dict] = field(default_factory=list)  # {symbol, time}
    max_concurrent_plays: int = 3
    max_new_risk_pct: float = 6.0  # aggregate open risk % of equity
    max_risk_per_trade_pct: float = 2.0
    cooldown_minutes: int = 60

    def record_stop_out(self, symbol: str, when: datetime | str | None = None) -> None:
        ts = _parse_ts(when) or datetime.now(timezone.utc)
        self.stop_outs.append({"symbol": str(symbol).upper(), "time": ts.isoformat()})

    def record_open(self, symbol: str, risk_pct: float) -> None:
        sym = str(symbol).upper()
        if sym not in self.open_symbols:
            self.open_symbols.append(sym)
        self.open_risk_pct = round(self.open_risk_pct + max(0.0, float(risk_pct)), 4)

    def record_close(self, symbol: str, risk_pct: float = 0.0) -> None:
        sym = str(symbol).upper()
        self.open_symbols = [s for s in self.open_symbols if s != sym]
        if risk_pct:
            self.open_risk_pct = max(0.0, round(self.open_risk_pct - float(risk_pct), 4))


@dataclass(frozen=True)
class RailDecision:
    allowed: bool
    reasons: List[str]

    @property
    def summary(self) -> str:
        if self.allowed:
            return "Discipline rails: OK"
        return "Discipline rails blocked: " + "; ".join(self.reasons)


def symbol_in_cooldown(
    symbol: str,
    stop_outs: Sequence[Mapping],
    *,
    now: datetime | None = None,
    cooldown_minutes: int = 60,
) -> tuple[bool, str]:
    """True if symbol had a stop-out within cool-down window."""
    sym = str(symbol).upper()
    now = now or datetime.now(timezone.utc)
    window = timedelta(minutes=max(0, int(cooldown_minutes)))
    latest: Optional[datetime] = None
    for row in stop_outs:
        if str(row.get("symbol", "")).upper() != sym:
            continue
        ts = _parse_ts(row.get("time") or row.get("exit_time") or row.get("timestamp"))
        if ts is None:
            continue
        if latest is None or ts > latest:
            latest = ts
    if latest is None:
        return False, ""
    if now - latest < window:
        mins_left = int((window - (now - latest)).total_seconds() // 60) + 1
        return (
            True,
            f"{sym} in post-stop cool-down ({mins_left}m remaining; no revenge re-entry)",
        )
    return False, ""


def check_discipline_rails(
    *,
    symbol: str,
    proposed_risk_pct: float,
    state: SessionRiskState,
    now: datetime | None = None,
) -> RailDecision:
    """Enforce max concurrent plays, max aggregate risk, per-trade cap, cool-down."""
    reasons: List[str] = []
    sym = str(symbol).upper()
    risk = float(proposed_risk_pct or 0)

    if risk <= 0:
        reasons.append("proposed_risk_pct must be > 0")
    if risk > state.max_risk_per_trade_pct + 1e-9:
        reasons.append(
            f"Per-trade risk {risk:.2f}% exceeds max {state.max_risk_per_trade_pct:.2f}%"
        )

    open_count = len({s.upper() for s in state.open_symbols})
    # New symbol counts toward concurrent; adding to existing may be allowed
    if sym not in {s.upper() for s in state.open_symbols}:
        if open_count >= state.max_concurrent_plays:
            reasons.append(
                f"Max concurrent plays {state.max_concurrent_plays} reached "
                f"({open_count} open)"
            )
        projected = state.open_risk_pct + risk
        if projected > state.max_new_risk_pct + 1e-9:
            reasons.append(
                f"Aggregate risk {projected:.2f}% would exceed max "
                f"{state.max_new_risk_pct:.2f}%"
            )

    cooling, cool_msg = symbol_in_cooldown(
        sym,
        state.stop_outs,
        now=now,
        cooldown_minutes=state.cooldown_minutes,
    )
    if cooling:
        reasons.append(cool_msg)

    return RailDecision(allowed=len(reasons) == 0, reasons=reasons)


def filter_symbols_on_cooldown(
    symbols: Iterable[str],
    stop_outs: Sequence[Mapping],
    *,
    now: datetime | None = None,
    cooldown_minutes: int = 60,
) -> List[str]:
    blocked = []
    for s in symbols:
        ok, _ = symbol_in_cooldown(
            s, stop_outs, now=now, cooldown_minutes=cooldown_minutes
        )
        if ok:
            blocked.append(str(s).upper())
    return blocked
