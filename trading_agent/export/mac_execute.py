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


# --- Live place path (single-leg debit via place_order; multi-leg ready-only) ---

_MULTILEG_HINTS = (
    "condor",
    "iron",
    "spread",
    "butterfly",
    "calendar",
    "diagonal",
    "straddle",
    "strangle",
    "collar",
    "jade",
    "ratio",
)
_CREDIT_HINTS = (
    "credit",
    "short premium",
    "cash secured",
    "csp",
    "covered call",
    "sell premium",
    "short put",
    "short call",
)


def parse_expiration_date(raw: str) -> Optional[date]:
    """Parse YYYY-MM-DD or ISO datetime to a calendar date."""
    s = (raw or "").strip()
    if not s:
        return None
    try:
        if "T" in s or " " in s:
            ts = s.replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts)
            return dt.date()
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def format_occ_symbol(underlying: str, expiration: date, call_put: str, strike: float) -> str:
    """Schwab OCC: 6-char root + YYMMDD + C/P + strike*1000 (8 digits)."""
    root = underlying.upper().ljust(6)[:6]
    yymmdd = expiration.strftime("%y%m%d")
    cp = "C" if call_put.upper().startswith("C") else "P"
    strike_int = int(round(float(strike) * 1000))
    return f"{root}{yymmdd}{cp}{strike_int:08d}"


def _blob(order: ReadyOrder) -> str:
    return " ".join(
        [
            order.strategy or "",
            order.setup_id or "",
            order.side or "",
            order.notes or "",
            " ".join(order.method_tags or []),
        ]
    ).lower()


def is_multileg_options(order: ReadyOrder) -> bool:
    """True when package needs multi-leg builder (not supported for live auto)."""
    instrument = (order.instrument or "").lower()
    if instrument not in ("options", "option"):
        return False
    if len(order.strike_prices or []) >= 2:
        return True
    blob = _blob(order)
    return any(h in blob for h in _MULTILEG_HINTS)


def is_credit_options(order: ReadyOrder) -> bool:
    """Credit / short-premium — do not BUY_TO_OPEN as a debit scalp."""
    blob = _blob(order)
    if any(h in blob for h in _CREDIT_HINTS):
        return True
    # Explicit short side without long/debit wording
    side = (order.side or "").lower()
    if side in ("short", "credit") and "debit" not in blob and "long" not in blob:
        return True
    return False


def infer_call_put(order: ReadyOrder) -> Optional[str]:
    """Infer CALL or PUT for a single-leg debit. None if ambiguous/neutral."""
    blob = _blob(order)
    side = (order.side or "").lower().strip()
    # Explicit contract wording wins
    if "long call" in blob or "debit call" in blob or "buy call" in blob:
        return "CALL"
    if "long put" in blob or "debit put" in blob or "buy put" in blob:
        return "PUT"
    has_call = "call" in blob
    has_put = "put" in blob
    if has_call and not has_put:
        return "CALL"
    if has_put and not has_call:
        return "PUT"
    if side in ("long", "bull", "call", "buy"):
        return "CALL"
    if side in ("short", "bear", "put", "sell"):
        # For debit directional shorts we still buy puts
        if "credit" in blob or "sell" in blob and "put" not in blob:
            return None
        return "PUT"
    return None


def classify_place_path(order: ReadyOrder) -> str:
    """
    Return place path key:
      single_leg_debit | equity_buy | multi_leg_ready | credit_ready | unsupported
    """
    instrument = (order.instrument or "options").lower()
    if instrument in ("underlying", "equity", "etf", "stock", "shares"):
        side = (order.side or "").lower()
        if side in ("short", "sell", "bear") and "long" not in side:
            return "unsupported"  # no short equity auto
        return "equity_buy"
    if instrument not in ("options", "option"):
        return "unsupported"
    if is_multileg_options(order):
        return "multi_leg_ready"
    if is_credit_options(order):
        return "credit_ready"
    if len(order.strike_prices or []) != 1:
        return "unsupported"
    if infer_call_put(order) is None:
        return "unsupported"
    if not parse_expiration_date(order.expiration):
        return "unsupported"
    return "single_leg_debit"


def _apply_place_response(order: ReadyOrder, resp: Dict[str, Any], *, occ: str = "") -> ReadyOrder:
    """Map place_order MCP response onto ReadyOrder status."""
    order.broker_response = {**resp, **({"occ_symbol": occ} if occ else {})}
    if resp.get("error"):
        order.status = "failed"
        return order
    status = str(resp.get("status") or "").lower()
    if status == "submitted" or (resp.get("dry_run") is False and not resp.get("error")):
        order.status = "submitted"
        return order
    if status == "dry_run" or resp.get("dry_run") is True:
        # Live flag was set but MCP still dry-ran — treat as failed safety
        order.status = "failed"
        order.broker_response = {
            **resp,
            "message": "place_order returned dry_run despite live submit request",
        }
        return order
    # Unknown shape — leave ready for human if no hard error
    if resp.get("order_spec") and not resp.get("error"):
        order.status = "ready"
        order.broker_response = {
            **resp,
            "mode": "ready_only",
            "message": "place_order did not confirm submit; use ready_orders / TOS",
        }
        return order
    order.status = "failed"
    return order


def submit_single_leg_debit(order: ReadyOrder, *, live: bool) -> ReadyOrder:
    """BUY_TO_OPEN one OCC contract via schwab-mcp place_order."""
    exp = parse_expiration_date(order.expiration)
    cp = infer_call_put(order)
    if not exp or not cp or not order.strike_prices:
        order.status = "ready"
        order.broker_response = {
            "mode": "ready_only",
            "message": "single-leg debit missing expiration, CALL/PUT, or strike",
        }
        return order
    strike = float(order.strike_prices[0])
    occ = format_occ_symbol(order.symbol, exp, cp, strike)
    qty = max(1, int(order.quantity or 1))
    payload = {
        "symbol": occ,
        "quantity": qty,
        "instruction": "BUY_TO_OPEN",
        "asset_type": "OPTION",
        "order_type": "MARKET",
        "duration": "DAY",
        "session": "NORMAL",
        "dry_run": not live,
        "confirm_live": bool(live),
    }
    resp = call_schwab_mcp("place_order", payload)
    return _apply_place_response(order, resp, occ=occ)


def submit_equity_buy(order: ReadyOrder, *, live: bool) -> ReadyOrder:
    """BUY underlying shares via place_order (no bracket — stops managed elsewhere)."""
    qty = max(1, int(order.quantity or 1))
    payload = {
        "symbol": order.symbol.upper(),
        "quantity": qty,
        "instruction": "BUY",
        "asset_type": "EQUITY",
        "order_type": "MARKET",
        "duration": "DAY",
        "session": "NORMAL",
        "dry_run": not live,
        "confirm_live": bool(live),
    }
    resp = call_schwab_mcp("place_order", payload)
    return _apply_place_response(order, resp)


def submit_order(order: ReadyOrder, *, live: bool) -> ReadyOrder:
    """Attempt broker submit via Schwab MCP; default dry-run / ready-only.

    Live paths supported on this Mac's schwab-mcp-server:
      - single-leg **debit** options → ``place_order`` BUY_TO_OPEN (OCC)
      - simple **equity buy** → ``place_order`` BUY

    Multi-leg packages (iron condor, spreads, etc.) and credit shorts stay
    ``ready`` for human TOS — no multi-leg builder on MCP yet.
    """
    if order.status == "skipped":
        return order
    if not live:
        path = classify_place_path(order)
        order.status = "dry_run"
        order.broker_response = {
            "mode": "dry_run",
            "place_path": path,
            "message": (
                "Ready order written; set TRADING_AGENT_AUTO_TRADE_LIVE=1 to submit "
                f"(path={path})"
            ),
        }
        return order

    path = classify_place_path(order)

    if path == "single_leg_debit":
        return submit_single_leg_debit(order, live=True)

    if path == "equity_buy":
        return submit_equity_buy(order, live=True)

    if path == "multi_leg_ready":
        order.status = "ready"
        order.broker_response = {
            "mode": "ready_only",
            "place_path": path,
            "message": (
                "Multi-leg options package — no MCP multi-leg builder; "
                "enter in TOS from ready_orders.json"
            ),
        }
        return order

    if path == "credit_ready":
        order.status = "ready"
        order.broker_response = {
            "mode": "ready_only",
            "place_path": path,
            "message": (
                "Credit/short-premium not auto-submitted (debit BUY_TO_OPEN only); "
                "use TOS from ready_orders.json"
            ),
        }
        return order

    order.status = "ready"
    order.broker_response = {
        "mode": "ready_only",
        "place_path": path,
        "message": "No safe live place path; human TOS from ready_orders.json",
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
            path = o.broker_response.get("place_path")
            occ = o.broker_response.get("occ_symbol")
            extra = f" path={path}" if path else ""
            if occ:
                extra += f" occ={occ}"
            lines.append(f"   broker={mode}{extra}")
        if o.notes:
            lines.append(f"   notes: {o.notes[:120]}")
        lines.append("")
    lines.append(
        "Live auto: single-leg debit BUY_TO_OPEN via place_order only. "
        "Multi-leg/credit → TOS from ready_orders JSON."
    )
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
    use_oms: Optional[bool] = None,
) -> Dict[str, Any]:
    """Load local books, build ready orders, optionally submit via Schwab MCP.

    By default routes through the OMS pipeline (pretrade, audit, lots, manage).
    Set TRADING_AGENT_OMS=0 for legacy consume-only behavior.
    """
    _ = force_outside_window  # launchd scripts gate time; soft here
    if use_oms is None:
        use_oms = os.getenv("TRADING_AGENT_OMS", "1").strip().lower() not in (
            "0",
            "false",
            "no",
            "off",
        )
    if use_oms:
        from trading_agent.oms.pipeline import run_oms_consume

        return run_oms_consume(paths=paths, live=live, mark_processed=mark_processed)

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
            if orders[i].status == "submitted":
                processed.add(orders[i].order_id)
                submitted_ids.append(orders[i].order_id)
            elif not live and orders[i].status == "dry_run":
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
