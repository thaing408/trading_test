"""IBKR paper (or live) order helpers via ib_insync.

Separate from research-only OHLCV (`market_data/ibkr_ohlcv.py`).
Orders require IBKR_READONLY=0 and TRADING_AGENT_BROKER=ibkr.

Default target: TWS paper API port 7497.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_IB = None
_LAST_ERROR = ""


def ibkr_trade_config() -> Dict[str, Any]:
    return {
        "enabled": os.getenv("IBKR_ENABLED", "").strip().lower() in ("1", "true", "yes", "on"),
        "host": os.getenv("IBKR_HOST", "127.0.0.1").strip() or "127.0.0.1",
        "port": int(os.getenv("IBKR_PORT", "7497") or 7497),  # paper default
        # Distinct from research client id (17) to avoid collisions
        "client_id": int(os.getenv("IBKR_TRADE_CLIENT_ID", os.getenv("IBKR_CLIENT_ID", "27")) or 27),
        "readonly": os.getenv("IBKR_READONLY", "0").strip().lower()
        in ("1", "true", "yes", "on"),
        "timeout": float(os.getenv("IBKR_CONNECT_TIMEOUT", "15") or 15),
        "account": (os.getenv("IBKR_ACCOUNT", "") or "").strip(),
    }


def last_error() -> str:
    return _LAST_ERROR


def disconnect() -> None:
    global _IB
    with _LOCK:
        if _IB is not None:
            try:
                _IB.disconnect()
            except Exception:  # noqa: BLE001
                pass
            _IB = None


def _connect(*, allow_trade: bool):
    """Connect for trading (readonly must be False when allow_trade)."""
    global _IB, _LAST_ERROR
    cfg = ibkr_trade_config()
    if not cfg["enabled"]:
        _LAST_ERROR = "IBKR_ENABLED not set"
        return None
    if allow_trade and cfg["readonly"]:
        _LAST_ERROR = "IBKR_READONLY=1 — cannot place orders (set IBKR_READONLY=0 for paper trade)"
        return None
    try:
        from ib_insync import IB
    except ImportError:
        _LAST_ERROR = "ib_insync not installed"
        return None

    with _LOCK:
        if _IB is not None and _IB.isConnected():
            return _IB
        if _IB is not None:
            try:
                _IB.disconnect()
            except Exception:  # noqa: BLE001
                pass
            _IB = None

        ib = IB()
        try:
            kwargs = dict(
                host=cfg["host"],
                port=cfg["port"],
                clientId=cfg["client_id"],
                timeout=cfg["timeout"],
            )
            # Trading connect: readonly=False
            try:
                ib.connect(**kwargs, readonly=False if allow_trade else bool(cfg["readonly"]))
            except TypeError:
                ib.connect(**kwargs)
        except Exception as exc:  # noqa: BLE001
            _LAST_ERROR = f"connect failed {cfg['host']}:{cfg['port']}: {exc}"
            logger.warning("IBKR trade %s", _LAST_ERROR)
            try:
                ib.disconnect()
            except Exception:  # noqa: BLE001
                pass
            return None

        if not ib.isConnected():
            _LAST_ERROR = "not connected"
            return None
        _IB = ib
        _LAST_ERROR = ""
        logger.info(
            "IBKR trade connected %s:%s clientId=%s",
            cfg["host"],
            cfg["port"],
            cfg["client_id"],
        )
        return _IB


def place_equity_market(
    *,
    symbol: str,
    quantity: int,
    instruction: str,
    live: bool,
) -> Dict[str, Any]:
    """Place equity MARKET order on IBKR.

    instruction: BUY | SELL (equity).
    live=False → dry_run (no submit).
    """
    global _LAST_ERROR
    sym = (symbol or "").upper().strip()
    qty = max(1, int(quantity))
    side = (instruction or "").upper().strip()
    if side not in ("BUY", "SELL", "BUY_TO_OPEN", "SELL_TO_CLOSE"):
        return {"error": "bad_instruction", "message": f"unsupported {instruction}"}
    action = "BUY" if side.startswith("BUY") else "SELL"

    if not live:
        return {
            "status": "dry_run",
            "dry_run": True,
            "broker": "ibkr",
            "symbol": sym,
            "quantity": qty,
            "instruction": action,
            "message": "dry_run — not submitted to IBKR",
        }

    ib = _connect(allow_trade=True)
    if ib is None:
        return {"error": "not_connected", "message": _LAST_ERROR or "IBKR connect failed", "broker": "ibkr"}

    try:
        from ib_insync import MarketOrder, Stock
    except ImportError:
        return {"error": "no_ib_insync", "message": "pip install ib_insync"}

    try:
        contract = Stock(sym, "SMART", "USD")
        qualified = ib.qualifyContracts(contract)
        if not qualified or int(getattr(contract, "conId", 0) or 0) <= 0:
            return {
                "error": "unqualified_contract",
                "message": f"No IBKR security definition for equity {sym}",
                "broker": "ibkr",
                "symbol": sym,
            }
        order = MarketOrder(action, qty)
        cfg = ibkr_trade_config()
        if cfg["account"]:
            order.account = cfg["account"]
        trade = ib.placeOrder(contract, order)
        # brief wait for status
        ib.sleep(1.0)
        status = str(getattr(trade.orderStatus, "status", "") or "submitted")
        order_id = getattr(trade.order, "orderId", None)
        return {
            "status": status.lower() if status else "submitted",
            "dry_run": False,
            "broker": "ibkr",
            "symbol": sym,
            "quantity": qty,
            "instruction": action,
            "order_id": order_id,
            "orderStatus": {
                "status": status,
                "filled": getattr(trade.orderStatus, "filled", None),
                "avgFillPrice": getattr(trade.orderStatus, "avgFillPrice", None),
            },
        }
    except Exception as exc:  # noqa: BLE001
        _LAST_ERROR = str(exc)
        logger.exception("IBKR place_equity failed")
        return {"error": "place_failed", "message": str(exc), "broker": "ibkr"}


def place_option_market(
    *,
    underlying: str,
    expiration: str,
    right: str,
    strike: float,
    quantity: int,
    instruction: str,
    live: bool,
) -> Dict[str, Any]:
    """Place single-leg option MARKET (paper). expiration YYYY-MM-DD; right C/P."""
    global _LAST_ERROR
    if not live:
        return {
            "status": "dry_run",
            "dry_run": True,
            "broker": "ibkr",
            "underlying": underlying,
            "expiration": expiration,
            "right": right,
            "strike": strike,
            "quantity": quantity,
            "instruction": instruction,
        }

    ib = _connect(allow_trade=True)
    if ib is None:
        return {"error": "not_connected", "message": _LAST_ERROR, "broker": "ibkr"}

    try:
        from ib_insync import MarketOrder, Option
    except ImportError:
        return {"error": "no_ib_insync", "message": "pip install ib_insync"}

    try:
        from datetime import date as _date
        from datetime import datetime as _dt

        ymd = expiration.replace("-", "")[:8]
        if len(ymd) != 8 or not ymd.isdigit():
            return {
                "error": "bad_expiration",
                "message": f"expiration must be YYYY-MM-DD or YYYYMMDD, got {expiration!r}",
                "broker": "ibkr",
            }
        exp_d = _dt.strptime(ymd, "%Y%m%d").date()
        # Dual-path DTE: SPY/QQQ/IWM may be 0DTE; others min DTE > 2 (default 3)
        try:
            from trading_agent.export.option_dte_policy import dte_allowed, min_dte_for_symbol

            ok_dte, why_dte, dte = dte_allowed(underlying, exp_d)
            min_dte = min_dte_for_symbol(underlying)
            if not ok_dte:
                return {
                    "error": why_dte.split(":")[0] if why_dte else "dte_too_short",
                    "message": f"{why_dte} for {underlying} {ymd}",
                    "broker": "ibkr",
                    "dte": dte,
                    "min_dte": min_dte,
                }
        except Exception:
            min_dte = int(os.getenv("IBKR_MIN_OPTION_DTE", "1") or 1)
            dte = (exp_d - _date.today()).days
            if dte < min_dte:
                return {
                    "error": "dte_too_short",
                    "message": f"DTE {dte} < min {min_dte} for {underlying} {ymd}",
                    "broker": "ibkr",
                    "dte": dte,
                    "min_dte": min_dte,
                }

        cp = "C" if str(right).upper().startswith("C") else "P"
        side = "BUY" if str(instruction).upper().startswith("BUY") else "SELL"
        contract = Option(
            underlying.upper(),
            ymd,
            float(strike),
            cp,
            "SMART",
            currency="USD",
        )
        qualified = ib.qualifyContracts(contract)
        con_id = int(getattr(contract, "conId", 0) or 0)
        if not qualified or con_id <= 0:
            return {
                "error": "unqualified_contract",
                "message": (
                    f"No IBKR security definition for {underlying.upper()} "
                    f"{ymd} {cp}{float(strike):g} (Error 200 class)"
                ),
                "broker": "ibkr",
                "underlying": underlying.upper(),
                "expiration": expiration,
                "right": cp,
                "strike": float(strike),
            }
        order = MarketOrder(side, max(1, int(quantity)))
        cfg = ibkr_trade_config()
        if cfg["account"]:
            order.account = cfg["account"]
        trade = ib.placeOrder(contract, order)
        ib.sleep(1.0)
        status = str(getattr(trade.orderStatus, "status", "") or "submitted")
        return {
            "status": status.lower() if status else "submitted",
            "dry_run": False,
            "broker": "ibkr",
            "underlying": underlying.upper(),
            "expiration": expiration,
            "right": cp,
            "strike": float(strike),
            "quantity": int(quantity),
            "instruction": side,
            "order_id": getattr(trade.order, "orderId", None),
            "orderStatus": {"status": status},
            "localSymbol": getattr(contract, "localSymbol", None),
            "conId": con_id,
            "dte": dte,
        }
    except Exception as exc:  # noqa: BLE001
        _LAST_ERROR = str(exc)
        logger.exception("IBKR place_option failed")
        return {"error": "place_failed", "message": str(exc), "broker": "ibkr"}


def ping_trade_connection() -> Dict[str, Any]:
    """Connectivity check without placing an order."""
    cfg = ibkr_trade_config()
    if cfg["readonly"]:
        # still connect read-only for ping of accounts
        pass
    try:
        from ib_insync import IB
    except ImportError:
        return {"ok": False, "error": "ib_insync missing", **{k: cfg[k] for k in ("host", "port", "client_id")}}

    ib = IB()
    try:
        ib.connect(
            cfg["host"],
            cfg["port"],
            clientId=int(cfg["client_id"]) + 100,  # ephemeral ping id
            timeout=cfg["timeout"],
            readonly=True,
        )
        accts = list(ib.managedAccounts() or [])
        ib.disconnect()
        return {
            "ok": True,
            "host": cfg["host"],
            "port": cfg["port"],
            "accounts": accts,
            "readonly_env": cfg["readonly"],
            "trade_ready": not cfg["readonly"] and cfg["enabled"],
        }
    except Exception as exc:  # noqa: BLE001
        try:
            ib.disconnect()
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "error": str(exc), "host": cfg["host"], "port": cfg["port"]}
