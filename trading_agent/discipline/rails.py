"""Discipline rails: max concurrent risk / plays and post-stop cool-down (no revenge).

Douglas process + Steenbarger habit: predefined risk limits; do not re-enter
the same symbol after a session stop-out within the cool-down window.

Production book: stop-outs live under TRADING_AGENT_STOPOUT_FILE (or
~/.trading_agent/stopouts.json). Open risk comes from positions file /
brokerage via build_session_risk_state().
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from trading_agent.config import RiskConfig


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


def default_stopout_path() -> Path:
    env = os.getenv("TRADING_AGENT_STOPOUT_FILE", "").strip()
    if env:
        return Path(env)
    return Path.home() / ".trading_agent" / "stopouts.json"


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

    def apply_risk_config(self, risk_config: "RiskConfig") -> "SessionRiskState":
        """Copy RiskConfig discipline limits onto this state (always used on desk path)."""
        if hasattr(risk_config, "max_concurrent_plays"):
            self.max_concurrent_plays = int(risk_config.max_concurrent_plays)
        if hasattr(risk_config, "max_aggregate_risk_pct"):
            self.max_new_risk_pct = float(risk_config.max_aggregate_risk_pct)
        if hasattr(risk_config, "max_risk_per_trade_pct"):
            self.max_risk_per_trade_pct = float(risk_config.max_risk_per_trade_pct)
        if hasattr(risk_config, "stop_cooldown_minutes"):
            self.cooldown_minutes = int(risk_config.stop_cooldown_minutes)
        return self

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


def session_state_from_risk_config(risk_config: "RiskConfig") -> SessionRiskState:
    """Empty book with limits taken from RiskConfig (production default seed)."""
    return SessionRiskState().apply_risk_config(risk_config)


def load_stopout_book(path: str | Path | None = None) -> List[dict]:
    """Load durable stop-out events for cool-down (empty if missing)."""
    p = Path(path) if path else default_stopout_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data.get("stop_outs", data) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    out: List[dict] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        sym = str(row.get("symbol") or "").strip().upper()
        if not sym:
            continue
        out.append(
            {
                "symbol": sym,
                "time": row.get("time") or row.get("exit_time") or row.get("timestamp") or "",
                "reason": row.get("reason") or "stop_loss",
            }
        )
    return out


def save_stopout_book(stop_outs: Sequence[Mapping], path: str | Path | None = None) -> Path:
    p = Path(path) if path else default_stopout_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "stop_outs": [
            {
                "symbol": str(r.get("symbol", "")).upper(),
                "time": r.get("time") or r.get("exit_time") or "",
                "reason": r.get("reason") or "stop_loss",
            }
            for r in stop_outs
            if r.get("symbol")
        ]
    }
    p.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return p


def record_stopout_event(
    symbol: str,
    *,
    when: datetime | str | None = None,
    reason: str = "stop_loss",
    path: str | Path | None = None,
) -> Path:
    """Append a stop-out to the durable book (desk / intraday Exit path)."""
    p = Path(path) if path else default_stopout_path()
    existing = load_stopout_book(p)
    ts = _parse_ts(when) or datetime.now(timezone.utc)
    existing.append(
        {
            "symbol": str(symbol).upper(),
            "time": ts.isoformat(),
            "reason": reason,
        }
    )
    # Keep last 200 events
    existing = existing[-200:]
    return save_stopout_book(existing, p)


def build_session_risk_state(
    risk_config: "RiskConfig",
    *,
    open_symbols: Sequence[str] | None = None,
    open_risk_pct: float | None = None,
    stop_outs: Sequence[Mapping] | None = None,
    stopout_path: str | Path | None = None,
    positions_path: str | Path | None = None,
    fixture_mode: bool = False,
    per_position_risk_pct: float | None = None,
) -> SessionRiskState:
    """Production constructor: RiskConfig limits + open book + stop-out file.

    Loads positions via plan_loader when positions_path / env is set so max
    concurrent plays reflects real open risk. Loads stop-outs for cool-down.
    """
    state = session_state_from_risk_config(risk_config)

    # Stop-out cool-down book
    if stop_outs is not None:
        state.stop_outs = [
            {"symbol": str(r.get("symbol", "")).upper(), "time": r.get("time") or ""}
            for r in stop_outs
            if r.get("symbol")
        ]
    else:
        path = stopout_path
        if path is None:
            path = os.getenv("TRADING_AGENT_STOPOUT_FILE") or None
        state.stop_outs = load_stopout_book(path)

    # Open positions → concurrent + aggregate risk
    symbols: List[str] = []
    if open_symbols is not None:
        symbols = [str(s).upper() for s in open_symbols if s]
    else:
        pos_path = positions_path
        if pos_path is None:
            pos_path = os.getenv("TRADING_AGENT_POSITIONS_FILE") or None
        try:
            from trading_agent.intraday.plan_loader import load_positions

            positions = load_positions(str(pos_path) if pos_path else None, fixture_mode)
            symbols = [p.symbol.upper() for p in positions if p.symbol]
        except Exception:
            symbols = []

    unit = (
        per_position_risk_pct
        if per_position_risk_pct is not None
        else float(risk_config.max_risk_per_trade_pct)
    )
    state.open_symbols = list(dict.fromkeys(symbols))  # stable unique
    if open_risk_pct is not None:
        state.open_risk_pct = float(open_risk_pct)
    else:
        state.open_risk_pct = round(len(state.open_symbols) * unit, 4)

    return state


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
