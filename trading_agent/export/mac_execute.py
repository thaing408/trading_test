"""macOS auto-trade execution helpers (local books → ready orders / Schwab MCP).

Fail-closed by default:
- Never places orders unless TRADING_AGENT_AUTO_TRADE_LIVE=1 (or --live)
- Never requires work→home file sync; only local books
- Incomplete risk packages / cash books / expired entries are skipped
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
PT = ZoneInfo("America/Los_Angeles")


@dataclass
class ReadyOrder:
    """Normalized order intent for TOS / Schwab MCP."""

    order_id: str
    symbol: str
    action: str
    side: str
    instrument: str
    strategy: str
    setup_id: str
    entry: float
    stop: float
    target: float
    max_risk_dollars: float
    strike_prices: List[float] = field(default_factory=list)
    expiration: str = ""
    quantity: int = 0
    defined_risk: bool = True
    confidence: float = 0.0
    source_book: str = ""
    method_tags: List[str] = field(default_factory=list)
    notes: str = ""
    status: str = "ready"  # ready | skipped | dry_run | submitted | failed
    skip_reason: str = ""
    broker_response: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def default_state_dir() -> Path:
    return Path.home() / ".trading_agent"


def default_sync_dir() -> Path:
    raw = os.getenv("TRADING_AGENT_SYNC_DIR", "").strip()
    if raw:
        return Path(raw)
    return Path.home() / ".trading_agent" / "sync"


def schwab_mcp_python() -> Path:
    env = os.getenv("SCHWAB_MCP_PYTHON", "").strip()
    if env:
        return Path(env)
    return Path.home() / "schwab-mcp-server" / ".venv" / "bin" / "python"


def live_enabled(*, cli_live: bool = False) -> bool:
    if cli_live:
        return True
    return os.getenv("TRADING_AGENT_AUTO_TRADE_LIVE", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def book_candidates(
    *,
    trading_day: Optional[date] = None,
    extra_paths: Optional[Sequence[Path]] = None,
) -> List[Path]:
    """Local-only book discovery paths (no cross-host sync)."""
    day = trading_day or datetime.now(PT).date()
    sync = default_sync_dir()
    session = Path.home() / ".trading_agent" / "sessions" / day.isoformat()
    grok = Path.home() / ".grok" / "state"
    names = (
        "auto_trade_book.json",
        "qt_auto_trade_book.json",
        "gap_screener_book.json",
    )
    out: List[Path] = []
    if extra_paths:
        out.extend(Path(p) for p in extra_paths)
    for base in (sync, session, grok, Path.home() / ".researcher"):
        for name in names:
            out.append(base / name)
    # de-dupe preserve order
    seen: set[str] = set()
    uniq: List[Path] = []
    for p in out:
        key = str(p.resolve()) if p.exists() else str(p)
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    return uniq


def load_book(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        data["_path"] = str(path)
        return data
    except (OSError, json.JSONDecodeError):
        return None


def entry_fingerprint(entry: Dict[str, Any], source: str = "") -> str:
    """Content fingerprint (source path ignored) so sync+session copies de-dupe."""
    _ = source  # kept for call-site compatibility
    raw = "|".join(
        [
            str(entry.get("symbol") or ""),
            str(entry.get("action") or "ENTER"),
            str(entry.get("setup_id") or ""),
            str(entry.get("strategy") or ""),
            str(entry.get("entry") or ""),
            str(entry.get("stop") or ""),
            str(entry.get("target") or ""),
            str(entry.get("expiration") or ""),
            ",".join(str(s) for s in (entry.get("strike_prices") or [])),
            str(entry.get("trading_date") or entry.get("expires_at") or ""),
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def validate_enter(entry: Dict[str, Any]) -> Tuple[bool, str]:
    """Fail-closed gate for executable ENTER rows."""
    if str(entry.get("action") or "ENTER").upper() not in ("ENTER", "BUY", "SELL_TO_OPEN"):
        return False, "not_enter_action"
    if entry.get("auto_trade_eligible") is False:
        return False, "not_auto_eligible"
    sym = str(entry.get("symbol") or "").strip().upper()
    if not sym:
        return False, "missing_symbol"
    try:
        entry_px = float(entry.get("entry") or 0)
        stop = float(entry.get("stop") or 0)
        target = float(entry.get("target") or 0)
        risk = float(entry.get("max_risk_dollars") or 0)
    except (TypeError, ValueError):
        return False, "bad_numbers"
    if not (entry_px > 0 and stop > 0 and target > 0 and risk > 0):
        return False, "incomplete_risk_package"
    if stop == target:
        return False, "stop_eq_target"
    instrument = str(entry.get("instrument") or "options").lower()
    if instrument in ("options", "option"):
        strikes = entry.get("strike_prices") or []
        if not strikes:
            return False, "missing_strikes"
        if entry.get("defined_risk") is False:
            return False, "not_defined_risk"
    exp = str(entry.get("expires_at") or "").strip()
    if exp:
        try:
            # accept Z or offset
            ts = exp.replace("Z", "+00:00")
            exp_dt = datetime.fromisoformat(ts)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp_dt:
                return False, "expired"
        except ValueError:
            pass
    return True, ""


def size_quantity(entry: Dict[str, Any]) -> int:
    """Conservative contract/share size from max_risk_dollars."""
    try:
        risk = float(entry.get("max_risk_dollars") or 0)
        entry_px = float(entry.get("entry") or 0)
        stop = float(entry.get("stop") or 0)
    except (TypeError, ValueError):
        return 0
    instrument = str(entry.get("instrument") or "options").lower()
    if instrument in ("options", "option"):
        # risk dollars already at package level; 1 contract default if risk small
        per = max(risk, 1.0)
        # Prefer 1 lot for defined-risk packages sized by research
        return max(1, min(int(os.getenv("TRADING_AGENT_MAX_CONTRACTS", "2")), 1 if per < 500 else 2))
    # underlying: shares from stop distance
    risk_pts = abs(entry_px - stop)
    if risk_pts <= 0 or risk <= 0:
        return 0
    shares = int(risk // risk_pts)
    return max(0, min(shares, int(os.getenv("TRADING_AGENT_MAX_SHARES", "100"))))


def entries_from_book(book: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pull ENTER-like rows from auto_trade or gap books."""
    path = str(book.get("_path") or "")
    name = Path(path).name if path else ""
    if name == "gap_screener_book.json":
        # Gap book is research handoff; not direct ENTER unless continuation rows have risk package
        rows: List[Dict[str, Any]] = []
        for key in ("continuation", "entries", "candidates"):
            for row in book.get(key) or []:
                if not isinstance(row, dict):
                    continue
                if row.get("action") or row.get("entry") or row.get("strike_prices"):
                    rows.append(row)
        return rows
    if book.get("stay_in_cash"):
        return []
    return [e for e in (book.get("entries") or []) if isinstance(e, dict)]


def build_ready_orders(
    books: Sequence[Dict[str, Any]],
    *,
    processed: Optional[set[str]] = None,
) -> List[ReadyOrder]:
    processed = processed or set()
    orders: List[ReadyOrder] = []
    seen_fp: set[str] = set()
    for book in books:
        source = str(book.get("_path") or book.get("source") or "unknown")
        if book.get("stay_in_cash") and Path(source).name != "gap_screener_book.json":
            continue
        for entry in entries_from_book(book):
            fp = entry_fingerprint(entry, source)
            if fp in seen_fp:
                continue
            seen_fp.add(fp)
            ok, reason = validate_enter(entry)
            qty = size_quantity(entry) if ok else 0
            order = ReadyOrder(
                order_id=fp,
                symbol=str(entry.get("symbol") or "").upper(),
                action=str(entry.get("action") or "ENTER").upper(),
                side=str(entry.get("side") or ""),
                instrument=str(entry.get("instrument") or "options"),
                strategy=str(entry.get("strategy") or ""),
                setup_id=str(entry.get("setup_id") or ""),
                entry=float(entry.get("entry") or 0),
                stop=float(entry.get("stop") or 0),
                target=float(entry.get("target") or 0),
                max_risk_dollars=float(entry.get("max_risk_dollars") or 0),
                strike_prices=[float(s) for s in (entry.get("strike_prices") or [])],
                expiration=str(entry.get("expiration") or ""),
                quantity=qty,
                defined_risk=bool(entry.get("defined_risk", True)),
                confidence=float(entry.get("confidence") or 0),
                source_book=source,
                method_tags=list(entry.get("method_tags") or []),
                notes=str(entry.get("notes") or entry.get("thesis") or "")[:240],
            )
            if not ok:
                order.status = "skipped"
                order.skip_reason = reason
            elif qty <= 0 and order.instrument.lower() not in ("options", "option"):
                order.status = "skipped"
                order.skip_reason = "zero_size"
            elif fp in processed:
                order.status = "skipped"
                order.skip_reason = "already_processed"
            orders.append(order)
    return orders


def load_processed_ids(path: Path) -> set[str]:
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            return set(data.get("processed_ids") or [])
    except (OSError, json.JSONDecodeError):
        pass
    return set()


def save_processed_ids(path: Path, ids: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "host": socket.gethostname(),
        "processed_ids": sorted(ids)[-500:],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_ready_orders(
    orders: Sequence[ReadyOrder],
    *,
    out_dir: Optional[Path] = None,
    trading_day: Optional[date] = None,
    live: bool = False,
) -> Path:
    day = trading_day or datetime.now(PT).date()
    base = out_dir or (default_state_dir() / "ready_orders")
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"ready_orders_{day.isoformat()}.json"
    ready = [o for o in orders if o.status in ("ready", "dry_run", "submitted", "failed")]
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trading_date": day.isoformat(),
        "host": socket.gethostname(),
        "live": live,
        "order_count": len(ready),
        "skipped_count": sum(1 for o in orders if o.status == "skipped"),
        "orders": [o.to_dict() for o in orders],
        "broker_boundary": (
            "mac-local-execute; live requires TRADING_AGENT_AUTO_TRADE_LIVE=1; "
            "default is ready-orders + dry-run only"
        ),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    # also sync copy for local tools
    try:
        sync_copy = default_sync_dir() / "ready_orders.json"
        sync_copy.parent.mkdir(parents=True, exist_ok=True)
        sync_copy.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass
    return path


def call_schwab_mcp(tool: str, payload: Dict[str, Any], *, timeout: int = 120) -> Dict[str, Any]:
    """Invoke local schwab_mcp.mcp_stdio tool. Fail-closed on missing server."""
    py = schwab_mcp_python()
    if not py.is_file():
        return {"error": "schwab_mcp_python_missing", "path": str(py)}
    try:
        proc = subprocess.run(
            [str(py), "-m", "schwab_mcp.mcp_stdio", tool, json.dumps(payload)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": "schwab_mcp_invoke_failed", "message": str(exc)}
    text = (proc.stdout or "").strip()
    if proc.returncode != 0:
        return {
            "error": "schwab_mcp_nonzero",
            "returncode": proc.returncode,
            "stderr": (proc.stderr or "")[:500],
            "stdout": text[:500],
        }
    start = text.find("{")
    if start < 0:
        return {"error": "no_json", "stdout": text[:500]}
    try:
        return json.loads(text[start:])
    except json.JSONDecodeError as exc:
        return {"error": "bad_json", "message": str(exc), "stdout": text[:500]}


def submit_order(order: ReadyOrder, *, live: bool) -> ReadyOrder:
    """Attempt broker submit via Schwab MCP; default dry-run / ready-only."""
    if order.status == "skipped":
        return order
    if not live:
        order.status = "dry_run"
        order.broker_response = {
            "mode": "dry_run",
            "message": "Ready order written; set TRADING_AGENT_AUTO_TRADE_LIVE=1 to submit",
        }
        return order

    # Live path: try known MCP tools. Prefer dedicated book/auto tools, then previews.
    instrument = order.instrument.lower()
    payload_common = {
        "symbol": order.symbol,
        "side": order.side,
        "strategy": order.strategy,
        "setup_id": order.setup_id,
        "entry": order.entry,
        "stop": order.stop,
        "target": order.target,
        "max_risk_dollars": order.max_risk_dollars,
        "quantity": order.quantity,
        "dry_run": False,
        "source": "trading_agent_mac_execute",
        "order_id": order.order_id,
    }

    # 1) Book-aware tools if custom schwab-mcp-server provides them
    for tool in ("execute_auto_trade_entry", "auto_trade_enter", "place_auto_trade"):
        resp = call_schwab_mcp(tool, {**payload_common, **order.to_dict()})
        if not resp.get("error") or resp.get("error") not in (
            "schwab_mcp_python_missing",
            "schwab_mcp_invoke_failed",
        ):
            # tool may be unknown — continue on tool-not-found style errors
            err = str(resp.get("error") or resp.get("message") or "").lower()
            if "unknown" in err or "not found" in err or "no such" in err:
                continue
            if resp.get("error"):
                order.status = "failed"
                order.broker_response = resp
                return order
            order.status = "submitted"
            order.broker_response = resp
            return order

    # 2) QQQ scalp tool exists on home Mac (healthcheck) — only for QQQ underlying
    if order.symbol == "QQQ" and instrument in ("underlying", "equity", "etf"):
        resp = call_schwab_mcp(
            "auto_trade_qqq",
            {"dry_run": False, "force_enter": True, "signal": order.to_dict()},
        )
        if not resp.get("error"):
            order.status = "submitted"
            order.broker_response = resp
            return order
        # still try dry path info
        order.broker_response = resp

    # 3) Options: preview tools (jkoelker-style) — place only if preview_id returned
    if instrument in ("options", "option") and order.strike_prices:
        preview = call_schwab_mcp(
            "preview_option_order",
            {
                "symbol": order.symbol,
                "instruction": "BUY_TO_OPEN",
                "quantity": max(1, order.quantity),
                "strikes": order.strike_prices,
                "expiration": order.expiration,
                "strategy": order.strategy,
                "limit_price": order.entry,
            },
        )
        if preview.get("preview_id") and not preview.get("error"):
            placed = call_schwab_mcp(
                "place_previewed_order",
                {"preview_id": preview["preview_id"]},
            )
            if not placed.get("error"):
                order.status = "submitted"
                order.broker_response = {"preview": preview, "place": placed}
                return order
            order.status = "failed"
            order.broker_response = {"preview": preview, "place": placed}
            return order
        # No place capability — leave as ready for human TOS
        order.status = "ready"
        order.broker_response = {
            "mode": "ready_only",
            "message": "Live set but no supported Schwab MCP place tool for this options package",
            "preview_attempt": preview,
        }
        return order

    # 4) Equity bracket preview
    if instrument in ("underlying", "equity", "etf"):
        preview = call_schwab_mcp(
            "preview_bracket_order",
            {
                "symbol": order.symbol,
                "quantity": max(1, order.quantity),
                "instruction": "BUY" if "bull" in order.side.lower() or order.side.lower() == "long" else "SELL",
                "entry_price": order.entry,
                "take_profit_price": order.target,
                "stop_price": order.stop,
            },
        )
        if preview.get("preview_id") and not preview.get("error"):
            placed = call_schwab_mcp(
                "place_previewed_order",
                {"preview_id": preview["preview_id"]},
            )
            if not placed.get("error"):
                order.status = "submitted"
                order.broker_response = {"preview": preview, "place": placed}
                return order
            order.status = "failed"
            order.broker_response = {"preview": preview, "place": placed}
            return order
        order.status = "ready"
        order.broker_response = {
            "mode": "ready_only",
            "message": "Live set but equity place tool unavailable; ready order only",
            "preview_attempt": preview,
        }
        return order

    order.status = "ready"
    order.broker_response = {
        "mode": "ready_only",
        "message": "No MCP place path matched; human TOS from ready_orders.json",
    }
    return order


def format_checklist(orders: Sequence[ReadyOrder], *, live: bool) -> str:
    lines = [
        f"# Mac auto-trade consumer  host={socket.gethostname()}  live={live}",
        f"orders={len(orders)} ready={sum(1 for o in orders if o.status in ('ready','dry_run'))} "
        f"submitted={sum(1 for o in orders if o.status == 'submitted')} "
        f"skipped={sum(1 for o in orders if o.status == 'skipped')}",
        "",
    ]
    if not orders:
        lines.append("NO ORDERS — empty books or stay_in_cash")
        return "\n".join(lines)
    for i, o in enumerate(orders, 1):
        lines.append(
            f"{i}. [{o.status}] {o.action} {o.symbol} | {o.strategy} | {o.side} | "
            f"instr={o.instrument} | setup={o.setup_id}"
        )
        lines.append(
            f"   entry={o.entry} stop={o.stop} target={o.target} "
            f"risk$={o.max_risk_dollars} qty={o.quantity} strikes={o.strike_prices} exp={o.expiration}"
        )
        if o.skip_reason:
            lines.append(f"   skip={o.skip_reason}")
        if o.broker_response:
            mode = o.broker_response.get("mode") or o.broker_response.get("error") or "ok"
            lines.append(f"   broker={mode}")
        if o.notes:
            lines.append(f"   notes: {o.notes[:120]}")
        lines.append("")
    lines.append("TOS: open ready_orders JSON or match strikes/DTE in thinkorswim.")
    return "\n".join(lines)


def in_qt_window(now: Optional[datetime] = None) -> bool:
    """True during 9:30–9:50 America/New_York weekdays."""
    ts = now or datetime.now(ET)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc).astimezone(ET)
    else:
        ts = ts.astimezone(ET)
    if ts.weekday() >= 5:
        return False
    t = ts.time()
    return time(9, 30) <= t <= time(9, 50)


def in_consumer_window(now: Optional[datetime] = None) -> bool:
    """Active consumer window: 9:25–11:00 ET weekdays (covers QT + early desk)."""
    ts = now or datetime.now(ET)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc).astimezone(ET)
    else:
        ts = ts.astimezone(ET)
    if ts.weekday() >= 5:
        return False
    t = ts.time()
    return time(9, 25) <= t <= time(11, 0)


def run_consume(
    *,
    paths: Optional[Sequence[Path]] = None,
    live: bool = False,
    force_outside_window: bool = False,
    mark_processed: bool = True,
) -> Dict[str, Any]:
    """Load local books, build ready orders, optionally submit via Schwab MCP."""
    if not force_outside_window and not in_consumer_window() and not os.getenv(
        "TRADING_AGENT_AUTO_TRADE_ANYTIME", ""
    ).strip():
        # Still allow dry inventory when forced via env or caller
        pass  # soft: still process books (launchd scripts gate time)

    candidates = list(paths) if paths else book_candidates()
    books: List[Dict[str, Any]] = []
    found_paths: List[str] = []
    for p in candidates:
        book = load_book(Path(p))
        if book:
            books.append(book)
            found_paths.append(str(p))

    state_path = default_state_dir() / "auto_trade_processed.json"
    processed = load_processed_ids(state_path)
    orders = build_ready_orders(books, processed=processed)

    submitted_ids: List[str] = []
    for i, order in enumerate(orders):
        if order.status == "skipped":
            continue
        orders[i] = submit_order(order, live=live)
        if orders[i].status in ("submitted", "dry_run", "ready") and mark_processed:
            # only mark submitted/failed-finalized as processed when live submitted
            if orders[i].status == "submitted":
                processed.add(orders[i].order_id)
                submitted_ids.append(orders[i].order_id)
            elif not live and orders[i].status == "dry_run":
                # dry-run does not mark processed so live later can still act
                pass

    if mark_processed and submitted_ids:
        save_processed_ids(state_path, processed)

    out_path = write_ready_orders(orders, live=live)
    text = format_checklist(orders, live=live)
    return {
        "books": found_paths,
        "orders": [o.to_dict() for o in orders],
        "ready_orders_path": str(out_path),
        "live": live,
        "checklist": text,
        "submitted_ids": submitted_ids,
    }
