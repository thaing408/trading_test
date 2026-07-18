#!/usr/bin/env python3
"""macOS auto-trade book consumer.

Loads local auto_trade_book / qt_auto_trade_book (never work↔home file sync),
writes ready_orders JSON, and optionally submits via local Schwab MCP.

Default is fail-closed dry-run (ready orders + checklist only).
Live placement requires --live or TRADING_AGENT_AUTO_TRADE_LIVE=1.

Usage:
  python scripts/macos/consume_auto_trade_book.py
  python scripts/macos/consume_auto_trade_book.py --live
  python scripts/macos/consume_auto_trade_book.py --watch --poll-seconds 60
  python scripts/macos/consume_auto_trade_book.py /path/to/book.json
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Allow running from repo without install
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _load_env_files() -> None:
    """Load home env; AUTO_TRADE_* / TRADING_AGENT_* always refresh from file."""
    for p in (
        Path.home() / ".grok" / "trading-agent.env",
        Path.home() / ".grok" / "discord.env",
        _REPO / ".env",
    ):
        if not p.is_file():
            continue
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if not k:
                    continue
                if k.startswith("AUTO_TRADE_") or k.startswith("TRADING_AGENT_"):
                    os.environ[k] = v
                elif k not in os.environ:
                    os.environ[k] = v
        except OSError:
            continue


def _log_unified_universe() -> None:
    """Align consumer with scalp bot: log shared desk+movers universe if present."""
    import json

    for p in (
        Path.home() / ".grok" / "state" / "auto_trade_universe.json",
        Path.home() / ".trading_agent" / "sync" / "auto_trade_universe.json",
    ):
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            syms = data.get("scan_symbols") or data.get("symbols") or []
            print(
                f"[unified] {p.name}: n={len(syms)} source={data.get('source')} "
                f"system={data.get('system')} movers={data.get('movers_symbols')}",
                flush=True,
            )
            return
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue


def main(argv: list[str] | None = None) -> int:
    _load_env_files()
    _log_unified_universe()
    parser = argparse.ArgumentParser(description="Consume local auto-trade books on macOS")
    parser.add_argument(
        "book",
        nargs="*",
        help="Optional explicit book path(s); default: local sync/session discovery",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Attempt Schwab MCP order placement (default: dry-run ready orders only)",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Poll for book changes until end of consumer window",
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=int(os.getenv("TRADING_AGENT_AUTO_TRADE_POLL", "60")),
        help="Watch poll interval (default 60)",
    )
    parser.add_argument(
        "--anytime",
        action="store_true",
        help="Ignore 9:25–11:00 ET window (also TRADING_AGENT_AUTO_TRADE_ANYTIME=1)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Less stdout (still writes ready_orders)",
    )
    args = parser.parse_args(argv)

    from trading_agent.export.mac_execute import (
        in_consumer_window,
        live_enabled,
        run_consume,
    )

    if args.anytime:
        os.environ["TRADING_AGENT_AUTO_TRADE_ANYTIME"] = "1"

    live = live_enabled(cli_live=bool(args.live))
    paths = [Path(p) for p in args.book] if args.book else None

    def once(*, allow_outside: bool = False) -> int:
        outside = not in_consumer_window()
        if outside and not (args.anytime or allow_outside or os.getenv(
            "TRADING_AGENT_AUTO_TRADE_ANYTIME", ""
        ).strip()):
            if not args.quiet:
                print("Outside consumer window (9:25–11:00 ET) — use --anytime to force")
            return 0
        result = run_consume(
            paths=paths,
            live=live,
            force_outside_window=bool(args.anytime or allow_outside),
            mark_processed=True,
        )
        if not args.quiet:
            print(result["checklist"])
            print(f"ready_orders: {result['ready_orders_path']}")
            if result["books"]:
                print("books:", ", ".join(result["books"]))
            else:
                print("books: (none found — run local research/QT or pass a path)")
        if not result["books"]:
            return 1
        return 0

    if not args.watch:
        return once()

    # Watch loop: process while in consumer window (or forever with --anytime)
    code = 0
    last_sig = ""
    # If launchd starts slightly early, wait until window opens (max ~30 min)
    wait_deadline = time.time() + 30 * 60
    while not in_consumer_window() and not args.anytime:
        if time.time() > wait_deadline:
            if not args.quiet:
                print("Timed out waiting for consumer window")
            return 0
        time.sleep(15)

    while True:
        if not args.anytime and not in_consumer_window():
            if not args.quiet:
                print("Consumer window ended — exiting watch")
            break
        from trading_agent.export.mac_execute import book_candidates

        cands = paths or book_candidates()
        sig_parts = []
        for p in cands:
            pp = Path(p)
            if pp.is_file():
                try:
                    sig_parts.append(f"{pp}:{pp.stat().st_mtime_ns}")
                except OSError:
                    pass
        sig = "|".join(sig_parts)
        if sig != last_sig or not last_sig:
            last_sig = sig
            code = once(allow_outside=bool(args.anytime))
        time.sleep(max(5, int(args.poll_seconds)))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
