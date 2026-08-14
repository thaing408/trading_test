"""Load Daily Trading Plan context and open positions."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, List, Mapping

from trading_agent.intraday.models import OpenPosition

logger = logging.getLogger(__name__)

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"

# Placeholders / junk rows that should never drive desk actions.
_INVALID_SYMBOLS = frozenset({"", "none", "null", "nan", "n/a", "-", "--", "cash", "usd"})


def _clean_symbol(raw: Any) -> str | None:
    if raw is None:
        return None
    symbol = str(raw).strip()
    if not symbol:
        return None
    if symbol.lower() in _INVALID_SYMBOLS:
        return None
    # JSON null sometimes becomes the literal string "None"
    if symbol == "None":
        return None
    return symbol


def _positive_qty(raw: Any) -> int | None:
    """Return open size if strictly positive; otherwise None (flat / closed)."""
    try:
        qty = float(raw if raw is not None else 0)
    except (TypeError, ValueError):
        return None
    if qty == 0 or abs(qty) < 1e-9:
        return None
    return max(1, int(abs(qty)))


def position_from_row(row: Mapping[str, Any]) -> OpenPosition | None:
    """Build an OpenPosition from a JSON/brokerage row, or None if not tradeable."""
    symbol = _clean_symbol(row.get("symbol"))
    if not symbol:
        return None

    qty = _positive_qty(row.get("quantity", row.get("qty", 1)))
    if qty is None:
        return None

    try:
        entry = float(row.get("entry_price") or row.get("avg_entry_price") or 0)
    except (TypeError, ValueError):
        entry = 0.0
    try:
        current = float(row.get("current_price") or entry or 0)
    except (TypeError, ValueError):
        current = entry

    # Zero-price junk rows fire false stop-loss (price 0 <= any stop).
    if entry <= 0 and current <= 0:
        return None

    try:
        stop = float(row.get("stop_loss") if row.get("stop_loss") is not None else entry * 0.95)
    except (TypeError, ValueError):
        stop = entry * 0.95 if entry else 0.0
    try:
        target = float(
            row.get("profit_target") if row.get("profit_target") is not None else entry * 1.05
        )
    except (TypeError, ValueError):
        target = entry * 1.05 if entry else 0.0

    strikes = row.get("strike_prices") or []
    if not isinstance(strikes, list):
        strikes = []

    instr = str(row.get("instrument_type") or row.get("asset_type") or "equity").lower()
    if "option" in instr:
        instr = "option"
    else:
        instr = "equity"
    underlying = str(row.get("underlying") or "").strip().upper()
    if not underlying and instr == "option":
        # "PLTR 08/07/26 120 Put" style thesis/symbol fallback
        underlying = symbol.split()[0].upper() if symbol else ""

    return OpenPosition(
        symbol=symbol,
        strategy=str(row.get("strategy") or row.get("broker") or "position"),
        entry_price=entry if entry > 0 else current,
        stop_loss=stop,
        profit_target=target,
        strike_prices=[float(s) for s in strikes if s is not None],
        expiration=str(row.get("expiration") or ""),
        quantity=qty,
        thesis=str(row.get("thesis") or ""),
        original_probability=float(row.get("original_probability") or 0.5),
        original_confidence=float(row.get("original_confidence") or 60.0),
        current_price=current if current > 0 else entry,
        allows_averaging_down=bool(row.get("allows_averaging_down", False)),
        trailing_stop_pct=float(row.get("trailing_stop_pct") or 2.0),
        max_risk_dollars=float(row.get("max_risk_dollars") or 500.0),
        pending_entry=bool(row.get("pending_entry", False)),
        instrument_type=instr,
        underlying=underlying,
        mark_source=str(row.get("mark_source") or ("premium" if instr == "option" else "file")),
    )


def positions_from_payload(data: Mapping[str, Any] | list) -> List[OpenPosition]:
    """Normalize a positions.json-style payload into open (non-flat) positions only."""
    if isinstance(data, list):
        rows = data
    else:
        rows = data.get("positions", []) if isinstance(data, Mapping) else []
    out: List[OpenPosition] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        pos = position_from_row(row)
        if pos is not None:
            out.append(pos)
    return out


def refresh_schwab_positions_file(path: str | Path | None = None) -> bool:
    """Re-export Schwab MCP positions into trading_agent positions.json.

    Returns True on success. Fail-closed (returns False) on any error so manage
    can continue with the last good file rather than crash the desk.
    """
    out = Path(path or os.getenv("TRADING_AGENT_POSITIONS_FILE") or "").expanduser()
    if not out.parts:
        out = Path.home() / ".trading_agent" / "positions.json"
    script = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "macos"
        / "trading-agent-positions.py"
    )
    if not script.is_file():
        logger.warning("positions export script missing: %s", script)
        return False
    py = os.getenv("TRADING_AGENT_PYTHON") or sys.executable
    try:
        proc = subprocess.run(
            [py, str(script), str(out)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if proc.returncode != 0:
            logger.warning(
                "Schwab positions refresh failed (%s): %s",
                proc.returncode,
                (proc.stderr or proc.stdout or "")[:300],
            )
            return False
        logger.info("Schwab positions refreshed -> %s (%s)", out, (proc.stdout or "").strip())
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Schwab positions refresh error: %s", exc)
        return False


def _maybe_seed_ibkr_positions_file(path: str | Path) -> bool:
    """When broker is IBKR, write positions.json from Gateway so desk can start.

    Paper me-ai has no Schwab MCP; missing positions.json previously aborted the
    whole session. Returns True if a file was written.
    """
    broker = (os.getenv("TRADING_AGENT_BROKER") or "").strip().lower()
    ibkr_on = (os.getenv("IBKR_ENABLED") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if broker not in ("ibkr", "ib") and not ibkr_on:
        return False
    out = Path(path).expanduser()
    try:
        from trading_agent.discord.paper_activity import fetch_ibkr_positions

        rows = fetch_ibkr_positions() or []
        payload = {
            "schema_version": 1,
            "source": "ibkr",
            "positions": [
                {
                    "symbol": r.get("symbol") or r.get("localSymbol"),
                    "quantity": r.get("quantity") or r.get("qty"),
                    "entry_price": r.get("average_price")
                    or r.get("avg_cost")
                    or r.get("entry_price")
                    or r.get("avg"),
                    "current_price": r.get("market_price")
                    or r.get("current_price")
                    or r.get("mkt")
                    or r.get("average_price")
                    or 0,
                    "strategy": "ibkr_paper",
                    "thesis": "IBKR paper open position",
                    "instrument_type": (
                        "option"
                        if str(r.get("secType") or "").upper() in ("OPT", "FOP")
                        else "equity"
                    ),
                    "expiration": r.get("expiration") or "",
                    "strike_prices": r.get("strike_prices") or [],
                }
                for r in rows
                if r.get("symbol") or r.get("localSymbol")
            ],
        }
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info(
            "IBKR positions seeded -> %s (%s rows)",
            out,
            len(payload["positions"]),
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("IBKR positions seed failed: %s", exc)
        # Still create an empty book so the desk can open without FileNotFoundError
        try:
            if not out.is_file():
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(
                    json.dumps(
                        {"schema_version": 1, "source": "empty", "positions": []},
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                logger.info("Wrote empty positions book -> %s", out)
                return True
        except Exception as write_exc:  # noqa: BLE001
            logger.warning("Could not write empty positions: %s", write_exc)
        return False


def load_positions(
    path: str | None,
    fixture_mode: bool,
    *,
    refresh: bool | None = None,
) -> List[OpenPosition]:
    """Load open positions: explicit file → fixture → optional brokerage → empty.

    Live path never synthesizes demo positions when brokerage is unconfigured.
    Flat (qty 0), blank/`None` symbols, and zero-price junk rows are dropped so
    the desk does not alert on already-closed names (e.g. TSLA after exit).

    When ``refresh`` is True (or env TRADING_AGENT_REFRESH_POSITIONS=1 and path
    is set and not fixture), re-pull Schwab before reading the file so manage
    Discord is not stuck on the 01:55 export.
    """
    if refresh is None:
        refresh = (
            not fixture_mode
            and bool(path)
            and os.getenv("TRADING_AGENT_REFRESH_POSITIONS", "1").strip().lower()
            not in ("0", "false", "no", "off")
        )
    if refresh and path and not fixture_mode:
        # Schwab export is a no-op / fail on IBKR-only paper hosts (me-ai).
        refresh_schwab_positions_file(path)
        _maybe_seed_ibkr_positions_file(path)

    if path:
        p = Path(path).expanduser()
        if not p.is_file():
            # Paper IBKR desk used to hard-crash here when Schwab refresh never
            # created the file (FileNotFoundError aborted session on me-ai).
            logger.warning(
                "positions file missing (%s) — empty open book for this run",
                p,
            )
            _maybe_seed_ibkr_positions_file(str(p))
            if p.is_file():
                with p.open(encoding="utf-8") as handle:
                    return positions_from_payload(json.load(handle))
            return []
        with p.open(encoding="utf-8") as handle:
            data = json.load(handle)
        return positions_from_payload(data)
    if fixture_mode:
        with (FIXTURE_DIR / "open_positions.json").open(encoding="utf-8") as handle:
            data = json.load(handle)
        return positions_from_payload(data)

    # Optional brokerage (Alpaca / Tradier) — fail closed
    try:
        from trading_agent.providers.brokerage import load_broker_positions
        from trading_agent.providers.config import ProviderConfig

        result = load_broker_positions(ProviderConfig.from_env())
        if result.ok and result.positions:
            mapped: List[dict] = []
            for row in result.positions:
                mapped.append(
                    {
                        "symbol": row.get("symbol"),
                        "quantity": row.get("qty"),
                        "entry_price": row.get("avg_entry_price") or row.get("current_price"),
                        "current_price": row.get("current_price"),
                        "strategy": str(row.get("broker") or "brokerage"),
                        "thesis": f"Brokerage position via {row.get('broker') or 'unknown'}",
                        "expiration": "",
                        "strike_prices": [],
                    }
                )
            return positions_from_payload({"positions": mapped})
    except Exception:
        pass
    return []


def load_plan_context(path: str | None, fixture_mode: bool) -> dict:
    if path:
        with Path(path).open(encoding="utf-8") as handle:
            return json.load(handle)
    if fixture_mode:
        with (FIXTURE_DIR / "daily_plan_context.json").open(encoding="utf-8") as handle:
            return json.load(handle)
    return {
        "overall_market_bias": "Neutral",
        "market_environment_score": 50.0,
        "market_regime": "neutral",
        "top_watchlist": [],
        "news_highlights": [],
        "high_impact_events": [],
        "stay_in_cash": True,
    }
