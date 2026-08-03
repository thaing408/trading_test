#!/usr/bin/env python3
"""Ping IBKR TWS/Gateway for research-only historical OHLCV.

Research only — never places orders. Requires:
  - TWS or IB Gateway running with API socket enabled
  - Read-Only API recommended in TWS API settings
  - pip install ib_insync
  - IBKR_ENABLED=1

Usage:
  IBKR_ENABLED=1 python scripts/ibkr_research_ping.py
  IBKR_ENABLED=1 IBKR_PORT=7496 python scripts/ibkr_research_ping.py --symbol QQQ
  IBKR_ENABLED=1 TRADING_AGENT_MARKET_DATA=ibkr python scripts/ibkr_research_ping.py --via-provider
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Repo root on path when run as scripts/...
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="IBKR research connectivity ping")
    parser.add_argument("--symbol", default="SPY", help="Symbol for sample bars (default SPY)")
    parser.add_argument("--period", default="5d", help="History period (default 5d)")
    parser.add_argument("--interval", default="1d", help="Bar interval (default 1d)")
    parser.add_argument(
        "--via-provider",
        action="store_true",
        help="Use market_data.get_ohlcv (full provider chain) instead of direct IBKR",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    args = parser.parse_args()

    if args.via_provider:
        from trading_agent.market_data.provider import get_ohlcv, last_ohlcv_source, reset_ohlcv_cache

        reset_ohlcv_cache()
        bars = get_ohlcv(args.symbol.upper(), interval=args.interval, period=args.period)
        out = {
            "mode": "provider",
            "symbol": args.symbol.upper(),
            "source": last_ohlcv_source(args.symbol.upper()),
            "bars": len(bars.get("close") or []),
            "last_close": (bars.get("close") or [None])[-1],
            "IBKR_ENABLED": os.getenv("IBKR_ENABLED", ""),
            "TRADING_AGENT_MARKET_DATA": os.getenv("TRADING_AGENT_MARKET_DATA", "auto"),
        }
        ok = out["bars"] > 0 and out["source"] == "ibkr"
    else:
        from trading_agent.market_data.ibkr_ohlcv import disconnect_ibkr, fetch_ibkr_ohlcv, ping_ibkr

        if args.symbol.upper() == "SPY" and args.period == "5d" and args.interval == "1d":
            out = ping_ibkr()
            out["mode"] = "direct"
            ok = bool(out.get("connected") and out.get("bars", 0) > 0)
        else:
            bars = fetch_ibkr_ohlcv(
                args.symbol.upper(), interval=args.interval, period=args.period
            )
            from trading_agent.market_data.ibkr_ohlcv import ibkr_config, last_ibkr_error

            cfg = ibkr_config()
            out = {
                "mode": "direct",
                "enabled": cfg["enabled"],
                "host": cfg["host"],
                "port": cfg["port"],
                "client_id": cfg["client_id"],
                "readonly": cfg["readonly"],
                "symbol": args.symbol.upper(),
                "bars": len(bars.get("close") or []),
                "last_close": (bars.get("close") or [None])[-1],
                "error": last_ibkr_error() or "",
            }
            ok = out["bars"] > 0
        disconnect_ibkr()

    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print("IBKR research ping")
        print("-" * 40)
        for k, v in out.items():
            print(f"  {k}: {v}")
        print("-" * 40)
        print("OK" if ok else "FAIL")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
