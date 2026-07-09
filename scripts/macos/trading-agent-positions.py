#!/usr/bin/env python3
"""Convert Schwab MCP get_positions JSON to trading_agent open_positions format."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
PYTHON = HOME / "schwab-mcp-server/.venv/bin/python"
DEFAULT_OUT = HOME / ".trading_agent/positions.json"

OCC_RE = re.compile(
    r"^([A-Z]{1,6})\s+(\d{6})([CP])(\d{8})$"
)


def _parse_occ(symbol: str) -> dict | None:
    normalized = " ".join(symbol.split())
    parts = normalized.split(" ", 1)
    if len(parts) == 2:
        candidate = f"{parts[0]}  {parts[1]}"
    else:
        candidate = normalized
    m = OCC_RE.match(candidate)
    if not m:
        return None
    root, yymmdd, cp, strike_raw = m.groups()
    yy, mm, dd = int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6])
    year = 2000 + yy
    strike = int(strike_raw) / 1000.0
    return {
        "underlying": root,
        "expiration": f"{year:04d}-{mm:02d}-{dd:02d}",
        "strike": strike,
        "option_type": "Call" if cp == "C" else "Put",
    }


def schwab_to_trading_agent(schwab_payload: dict) -> dict:
    positions: list[dict] = []
    for row in schwab_payload.get("positions", []):
        symbol = str(row.get("symbol", "")).strip()
        asset = str(row.get("asset_type", "EQUITY")).upper()
        qty = int(abs(float(row.get("quantity", 0) or 0)))
        if qty <= 0:
            continue
        avg = float(row.get("average_price") or 0)
        mkt = float(row.get("market_value") or 0)

        if asset == "OPTION":
            parsed = _parse_occ(symbol)
            underlying = parsed["underlying"] if parsed else symbol.split()[0]
            entry = avg if avg > 0 else max(mkt / max(qty * 100, 1), 0.01)
            current = mkt / max(qty * 100, 1) if mkt else entry
            strike = parsed["strike"] if parsed else entry
            expiry = parsed["expiration"] if parsed else "2099-12-31"
            strat = f"Long {parsed['option_type']}" if parsed else "Long Option"
            positions.append(
                {
                    "symbol": underlying,
                    "strategy": strat,
                    "entry_price": round(entry, 4),
                    "stop_loss": round(entry * 0.7, 4),
                    "profit_target": round(entry * 1.5, 4),
                    "strike_prices": [strike],
                    "expiration": expiry,
                    "quantity": qty,
                    "thesis": row.get("description") or f"Open {underlying} position",
                    "original_probability": 0.5,
                    "original_confidence": 60.0,
                    "current_price": round(current, 4),
                    "allows_averaging_down": False,
                    "trailing_stop_pct": 2.0,
                    "max_risk_dollars": round(entry * qty * 100, 2),
                }
            )
        else:
            entry = avg if avg > 0 else (mkt / qty if qty else 0)
            current = mkt / qty if qty and mkt else entry
            positions.append(
                {
                    "symbol": symbol,
                    "strategy": "Long Equity",
                    "entry_price": round(entry, 4),
                    "stop_loss": round(entry * 0.92, 4),
                    "profit_target": round(entry * 1.08, 4),
                    "strike_prices": [round(entry, 2)],
                    "expiration": "2099-12-31",
                    "quantity": qty,
                    "thesis": row.get("description") or f"Open {symbol} equity",
                    "original_probability": 0.5,
                    "original_confidence": 60.0,
                    "current_price": round(current, 4),
                    "allows_averaging_down": False,
                    "trailing_stop_pct": 2.0,
                    "max_risk_dollars": round(mkt, 2),
                }
            )
    return {"positions": positions}


def fetch_schwab_positions() -> dict:
    proc = subprocess.run(
        [str(PYTHON), "-m", "schwab_mcp.mcp_stdio", "get_positions", "{}"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "get_positions failed")
    text = proc.stdout.strip()
    start = text.find("{")
    if start < 0:
        raise RuntimeError(f"No JSON in get_positions output: {text[:200]}")
    return json.loads(text[start:])


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    raw = fetch_schwab_positions()
    if raw.get("error"):
        raise RuntimeError(raw.get("message", "Schwab API error"))
    converted = schwab_to_trading_agent(raw)
    out.write_text(json.dumps(converted, indent=2) + "\n")
    print(f"wrote {len(converted['positions'])} positions -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())