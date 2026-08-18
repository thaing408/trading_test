"""Mac execute-side health: cash, ready orders, consumer process, OMS summary."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _state_home(state: Path | None = None) -> Path:
    return Path(state) if state else Path.home() / ".trading_agent"


def load_account_cash(*, state: Path | None = None) -> Dict[str, Any]:
    """Best-effort cash snapshot: OMS audit consume_start or live fetch on Mac."""
    out: Dict[str, Any] = {
        "fetched": False,
        "cash_available": None,
        "buying_power": None,
        "tradable_after_reserve": None,
        "reserve": None,
        "source": None,
        "error": None,
    }
    root = _state_home(state)
    # Prefer latest consume_start audit payload (no live broker call from UI)
    audit_dir = root / "oms" / "audit"
    if audit_dir.is_dir():
        files = sorted(audit_dir.glob("audit_*.jsonl"), reverse=True)
        for fp in files[:3]:
            try:
                lines = fp.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in reversed(lines[-200:]):
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("event") != "consume_start":
                    continue
                pre = (ev.get("payload") or {}).get("pretrade") or {}
                ac = pre.get("account_cash") or (ev.get("payload") or {}).get("account_cash") or {}
                if isinstance(ac, dict) and (ac.get("fetched") or ac.get("cash_available") is not None):
                    out.update(
                        {
                            "fetched": bool(ac.get("fetched")),
                            "cash_available": ac.get("cash_available"),
                            "buying_power": ac.get("buying_power"),
                            "tradable_after_reserve": ac.get("tradable_after_reserve"),
                            "reserve": ac.get("reserve"),
                            "source": f"audit:{fp.name}",
                            "ts": ev.get("ts"),
                            "metric": ac.get("metric"),
                            "error": ac.get("error"),
                        }
                    )
                    return out
    # Optional live fetch (Mac only, env opt-in — avoid slowing UI)
    if os.getenv("TRADING_AGENT_UI_LIVE_CASH", "0").strip() in ("1", "true", "yes"):
        try:
            from trading_agent.export import mac_execute as mx
            from trading_agent.oms.broker import fetch_account_balances, parse_tradable_cash
            from trading_agent.oms.pretrade import PretradeConfig

            if str(mx.broker_name() or "").lower() == "ibkr":
                from trading_agent.oms.ibkr_broker import fetch_ibkr_account_balances

                resp = fetch_ibkr_account_balances()
            else:
                resp = fetch_account_balances(lambda t, p: mx.call_schwab_mcp(t, p))
            cfg = PretradeConfig.from_env()
            raw = parse_tradable_cash(resp, prefer=cfg.cash_metric)
            bal = resp.get("balances") or {}
            reserve = float(cfg.min_cash_reserve or 0)
            out.update(
                {
                    "fetched": not bool(resp.get("error")),
                    "cash_available": bal.get("cash_available"),
                    "buying_power": bal.get("buying_power"),
                    "tradable_after_reserve": None
                    if raw is None
                    else max(0.0, float(raw) - reserve),
                    "reserve": reserve,
                    "source": "live",
                    "error": resp.get("error"),
                }
            )
        except Exception as exc:  # noqa: BLE001
            out["error"] = str(exc)
    return out


def load_ready_orders(*, trading_date: str, state: Path | None = None) -> Dict[str, Any]:
    root = _state_home(state)
    path = root / "ready_orders" / f"ready_orders_{trading_date}.json"
    sync = root / "sync" / "ready_orders.json"
    chosen = path if path.is_file() else (sync if sync.is_file() else path)
    out: Dict[str, Any] = {
        "path": str(chosen),
        "exists": chosen.is_file(),
        "orders": [],
        "counts": {"submitted": 0, "skipped": 0, "failed": 0, "ready": 0, "dry_run": 0, "other": 0},
        "mtime_iso": None,
    }
    if not chosen.is_file():
        return out
    try:
        st = chosen.stat()
        out["mtime_iso"] = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
        data = json.loads(chosen.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        out["error"] = str(exc)
        return out
    orders = data.get("orders") if isinstance(data, dict) else data
    if not isinstance(orders, list):
        orders = []
    rows = []
    for o in orders:
        if not isinstance(o, dict):
            continue
        status = str(o.get("status") or "other").lower()
        key = status if status in out["counts"] else "other"
        out["counts"][key] = int(out["counts"].get(key) or 0) + 1
        rows.append(
            {
                "symbol": o.get("symbol"),
                "status": status,
                "skip_reason": o.get("skip_reason"),
                "side": o.get("side"),
                "action": o.get("action"),
                "expiration": o.get("expiration"),
                "quantity": o.get("quantity"),
                "max_risk_dollars": o.get("max_risk_dollars"),
                "strategy": (o.get("strategy") or "")[:60],
            }
        )
    out["orders"] = rows
    out["live"] = data.get("live") if isinstance(data, dict) else None
    return out


def load_consumer_health(*, state: Path | None = None) -> Dict[str, Any]:
    """Consumer process + last log heartbeat."""
    import subprocess

    root = _state_home(state)
    out: Dict[str, Any] = {
        "alive": False,
        "pids": [],
        "pidfile": None,
        "last_log_line": None,
        "watchdog_last": None,
    }
    try:
        proc = subprocess.run(
            ["pgrep", "-f", "consume_auto_trade_book.py"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        pids = [p for p in (proc.stdout or "").split() if p.strip()]
        out["pids"] = pids
        out["alive"] = bool(pids)
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)

    for name in ("auto-trade-consumer.pid", "auto-trade-consumer-watchdog.pid"):
        pf = root / name
        if pf.is_file():
            try:
                out["pidfile"] = {"path": str(pf), "value": pf.read_text().strip()}
            except OSError:
                pass
            break

    # Tail consumer log
    from datetime import date as date_cls
    from zoneinfo import ZoneInfo

    day = datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()
    logp = root / "logs" / f"auto-trade-consumer_{day}.log"
    if logp.is_file():
        try:
            lines = logp.read_text(encoding="utf-8", errors="replace").splitlines()
            out["last_log_line"] = lines[-1] if lines else None
            out["log_path"] = str(logp)
        except OSError:
            pass
    wlog = root / "logs" / f"auto-trade-watchdog_{day}.log"
    if wlog.is_file():
        try:
            lines = wlog.read_text(encoding="utf-8", errors="replace").splitlines()
            out["watchdog_last"] = lines[-1] if lines else None
        except OSError:
            pass
    return out


def load_oms_summary(*, state: Path | None = None) -> Dict[str, Any]:
    """Open lots enriched for UI + risk totals."""
    root = _state_home(state)
    try:
        from trading_agent.oms.state import OmsStore

        store = OmsStore(root=root / "oms" if (root / "oms").is_dir() else None)
        lots = []
        for lot in store.open_lots():
            d = lot.to_dict()
            meta = d.get("broker_meta") or {}
            d["trail_stop"] = meta.get("trail_stop_underlying")
            d["option_entry_premium"] = meta.get("option_entry_premium")
            d["initial_stop"] = meta.get("initial_stop")
            lots.append(d)
        return {
            "open_lots": len(lots),
            "open_risk": float(store.open_risk_dollars()),
            "day_realized_pnl": float(store.day_realized_pnl()),
            "lots": lots,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "open_lots": 0,
            "open_risk": 0.0,
            "day_realized_pnl": 0.0,
            "lots": [],
            "error": str(exc),
        }
