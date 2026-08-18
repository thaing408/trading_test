"""Scalp Pulse session halt card — names tickers (Mac pulse imports this).

Live QQQ Pulse historically posted:

    ⛔ Session HALTED — bot sleeve done for day
    2 losing scalps — done for day
    trips=2 W=0 L=2
    No more entries until next session (per-symbol signals suppressed).

That is a **sleeve** halt (max losing scalps, default 2) — not the desk OMS
2-round-trips-**per-ticker** gate. This module:

- records each closed scalp with **symbol / side / pnl**
- formats a halt card that lists **which names** lost
- still treats 2 sleeve losers as a full Pulse session halt

Mac ``~/.grok/scripts/scalp-market-pulse.py`` should call
``record_pulse_close`` on every fill close and
``format_session_halt_card`` / ``maybe_post_session_halt`` when halted.

CLI::

    python -m trading_agent research scalp-halt --record --symbol NVDA --side PUT --pnl -30
    python -m trading_agent research scalp-halt --card
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")

DEFAULT_MAX_LOSING = 2


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


def ledger_path(path: Optional[Path] = None) -> Path:
    if path is not None:
        return Path(path)
    raw = os.getenv("TRADING_AGENT_PULSE_LEDGER", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".trading_agent" / "scalp" / "pulse_session.json"


def session_date_pt(now: Optional[datetime] = None) -> str:
    ts = now or datetime.now(PT)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=PT)
    else:
        ts = ts.astimezone(PT)
    return ts.date().isoformat()


@dataclass
class PulseClose:
    symbol: str
    side: str = ""
    pnl: float = 0.0
    setup: str = ""
    reason: str = ""
    ts: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PulseClose":
        return cls(
            symbol=str(data.get("symbol") or "").upper(),
            side=str(data.get("side") or "").upper(),
            pnl=float(data.get("pnl") or 0.0),
            setup=str(data.get("setup") or ""),
            reason=str(data.get("reason") or ""),
            ts=str(data.get("ts") or ""),
        )


@dataclass
class PulseLedger:
    session_date: str
    max_losing_scalps: int = DEFAULT_MAX_LOSING
    closes: List[PulseClose] = field(default_factory=list)
    halt_posted: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "session_date": self.session_date,
            "max_losing_scalps": self.max_losing_scalps,
            "closes": [c.as_dict() for c in self.closes],
            "halt_posted": self.halt_posted,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PulseLedger":
        raw = data.get("closes") or []
        closes = [PulseClose.from_dict(x) for x in raw if isinstance(x, dict)]
        try:
            cap = int(data.get("max_losing_scalps") or DEFAULT_MAX_LOSING)
        except (TypeError, ValueError):
            cap = DEFAULT_MAX_LOSING
        return cls(
            session_date=str(data.get("session_date") or ""),
            max_losing_scalps=max(1, cap),
            closes=closes,
            halt_posted=bool(data.get("halt_posted")),
        )


def empty_ledger(day: Optional[str] = None) -> PulseLedger:
    return PulseLedger(
        session_date=day or session_date_pt(),
        max_losing_scalps=max(1, _env_int("SCALP_MAX_LOSING", DEFAULT_MAX_LOSING)),
    )


def load_ledger(path: Optional[Path] = None, *, day: Optional[str] = None) -> PulseLedger:
    p = ledger_path(path)
    want = day or session_date_pt()
    if not p.is_file():
        return empty_ledger(want)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return empty_ledger(want)
    if not isinstance(data, dict):
        return empty_ledger(want)
    led = PulseLedger.from_dict(data)
    if led.session_date != want:
        return empty_ledger(want)
    return led


def save_ledger(led: PulseLedger, path: Optional[Path] = None) -> Path:
    p = ledger_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(led.as_dict(), indent=2) + "\n", encoding="utf-8")
    return p


def record_pulse_close(
    symbol: str,
    *,
    side: str = "",
    pnl: float = 0.0,
    setup: str = "",
    reason: str = "",
    path: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> PulseLedger:
    """Append a closed scalp and persist. Resets ledger when the PT date rolls."""
    day = session_date_pt(now)
    led = load_ledger(path, day=day)
    ts = now or datetime.now(PT)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=PT)
    led.closes.append(
        PulseClose(
            symbol=str(symbol or "").upper().strip(),
            side=str(side or "").upper().strip(),
            pnl=float(pnl),
            setup=str(setup or ""),
            reason=str(reason or ""),
            ts=ts.isoformat(),
        )
    )
    save_ledger(led, path)
    return led


def _is_loss(c: PulseClose) -> bool:
    return float(c.pnl) < 0


def _is_win(c: PulseClose) -> bool:
    return float(c.pnl) > 0


def sleeve_stats(led: PulseLedger) -> Dict[str, Any]:
    trips = len(led.closes)
    wins = sum(1 for c in led.closes if _is_win(c))
    losses = sum(1 for c in led.closes if _is_loss(c))
    by_sym: Dict[str, Dict[str, Any]] = {}
    for c in led.closes:
        sym = c.symbol or "?"
        row = by_sym.setdefault(
            sym,
            {"symbol": sym, "trips": 0, "wins": 0, "losses": 0, "pnl": 0.0, "closes": []},
        )
        row["trips"] += 1
        row["pnl"] = float(row["pnl"]) + float(c.pnl)
        if _is_win(c):
            row["wins"] += 1
        elif _is_loss(c):
            row["losses"] += 1
        row["closes"].append(c)
    return {
        "trips": trips,
        "wins": wins,
        "losses": losses,
        "by_symbol": by_sym,
        "max_losing": int(led.max_losing_scalps or DEFAULT_MAX_LOSING),
    }


def sleeve_halted(led: PulseLedger) -> bool:
    st = sleeve_stats(led)
    return int(st["losses"]) >= int(st["max_losing"])


def _side_label(c: PulseClose) -> str:
    side = (c.side or "").upper()
    if side in ("PUT", "P", "BEAR", "BEARISH", "SHORT"):
        return "PUT"
    if side in ("CALL", "C", "BULL", "BULLISH", "LONG"):
        return "CALL"
    return side or "?"


def format_session_halt_card(led: Optional[PulseLedger] = None) -> str:
    """Named halt card for #scalp-pulse (sleeve halt + per-ticker lines)."""
    book = led if led is not None else load_ledger()
    st = sleeve_stats(book)
    trips, wins, losses = st["trips"], st["wins"], st["losses"]
    cap = st["max_losing"]
    halted = losses >= cap

    losers = [c for c in book.closes if _is_loss(c)]
    loser_bits = [f"{c.symbol} {_side_label(c)}" for c in losers]
    loser_line = "  ".join(loser_bits) if loser_bits else "(no named losers in ledger)"

    lines: List[str] = []
    if halted:
        lines.append("⛔ Session HALTED — bot sleeve done for day")
        lines.append(f"{losses} losing scalps — done for day (cap {cap})")
    else:
        lines.append("Scalp Pulse — session open")
        lines.append(f"losers {losses}/{cap} — sleeve still live")

    lines.append(f"LOSERS: {loser_line}")
    lines.append(f"sleeve trips={trips} W={wins} L={losses}")

    by_sym: Dict[str, Dict[str, Any]] = st["by_symbol"]
    for sym in sorted(by_sym):
        row = by_sym[sym]
        parts = []
        for c in row["closes"]:
            mark = "L" if _is_loss(c) else ("W" if _is_win(c) else "F")
            parts.append(f"{_side_label(c)} {mark}")
        lines.append(
            f"  {sym}: trips={row['trips']} W={row['wins']} L={row['losses']}"
            f"  ({', '.join(parts)})"
        )

    if halted:
        lines.append(
            "No more Pulse entries until next session "
            "(sleeve halt — all tickers blocked, not per-name 2-RT)."
        )
    else:
        lines.append("Per-ticker desk OMS cap (2 RT) is separate from this Pulse sleeve halt.")
    return "\n".join(lines) + "\n"


def maybe_post_session_halt(
    led: Optional[PulseLedger] = None,
    *,
    path: Optional[Path] = None,
    post: bool = True,
) -> Dict[str, Any]:
    """Post the named halt card once when the sleeve first hits the loss cap."""
    book = led if led is not None else load_ledger(path)
    if not sleeve_halted(book):
        return {"posted": False, "reason": "not_halted", "card": format_session_halt_card(book)}
    if book.halt_posted:
        return {"posted": False, "reason": "already_posted", "card": format_session_halt_card(book)}
    card = format_session_halt_card(book)
    if not post:
        return {"posted": False, "reason": "dry_run", "card": card}
    try:
        from trading_agent.discord.config import DiscordConfig
        from trading_agent.discord.poster import post_message

        if not os.getenv("DISCORD_TOKEN") and os.getenv("DISCORD_BOT_TOKEN"):
            os.environ["DISCORD_TOKEN"] = os.environ["DISCORD_BOT_TOKEN"]
        channel = (
            os.getenv("DISCORD_SCALP_CHANNEL_ID")
            or os.getenv("DISCORD_ALERTS_CHANNEL_ID")
            or os.getenv("DISCORD_CHANNEL_ID")
        )
        if channel:
            os.environ["DISCORD_CHANNEL_ID"] = channel
        cfg = DiscordConfig.from_env()
        post_message(card, cfg, username="Scalp Pulse")
    except Exception as exc:  # noqa: BLE001
        return {"posted": False, "reason": f"discord:{exc}", "card": card}
    book.halt_posted = True
    save_ledger(book, path)
    return {"posted": True, "reason": "ok", "card": card}


def main(argv: Optional[List[str]] = None) -> int:
    """CLI: record a close, print card, optionally post halt once."""
    import argparse

    p = argparse.ArgumentParser(description="Scalp Pulse halt ledger / named card")
    p.add_argument("--record", action="store_true", help="Append a closed scalp")
    p.add_argument("--symbol", default="")
    p.add_argument("--side", default="")
    p.add_argument("--pnl", type=float, default=0.0)
    p.add_argument("--setup", default="")
    p.add_argument("--reason", default="")
    p.add_argument("--card", action="store_true", help="Print halt/status card")
    p.add_argument("--post", action="store_true", help="Post halt to Discord once if tripped")
    p.add_argument("--ledger", default="", help="Override ledger JSON path")
    args = p.parse_args(argv)
    path = Path(args.ledger).expanduser() if args.ledger else None
    led = load_ledger(path)
    if args.record:
        if not args.symbol:
            print("error: --record needs --symbol", file=__import__("sys").stderr)
            return 2
        led = record_pulse_close(
            args.symbol,
            side=args.side,
            pnl=args.pnl,
            setup=args.setup,
            reason=args.reason,
            path=path,
        )
    card = format_session_halt_card(led)
    if args.card or args.record or not args.post:
        print(card, end="")
    if args.post:
        out = maybe_post_session_halt(led, path=path, post=True)
        print(f"[pulse-halt] posted={out.get('posted')} {out.get('reason')}", file=__import__("sys").stderr)
    return 0


def record_lot_close(lot: Any, *, pnl: float, path: Optional[Path] = None) -> PulseLedger:
    """OMS hook — record a closed lot onto the Pulse ledger."""
    symbol = str(getattr(lot, "symbol", "") or "")
    side = str(getattr(lot, "side", "") or "")
    setup = str(getattr(lot, "setup_id", "") or getattr(lot, "strategy", "") or "")
    reason = str(getattr(lot, "exit_reason", "") or "")
    return record_pulse_close(
        symbol, side=side, pnl=float(pnl), setup=setup, reason=reason, path=path
    )


if __name__ == "__main__":
    raise SystemExit(main())
