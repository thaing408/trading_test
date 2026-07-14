#!/usr/bin/env python3
"""macOS helper: load Windows-exported auto_trade_book.json for TOS/MCP execution.

Does not place orders — prints a ready checklist for human or MCP agent.
Windows writes ~/.trading_agent/sync/auto_trade_book.json (or TRADING_AGENT_SYNC_DIR).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    sync = os.getenv("TRADING_AGENT_SYNC_DIR", "").strip()
    root = Path(sync) if sync else Path.home() / ".trading_agent" / "sync"
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "auto_trade_book.json"
    if not path.exists():
        print(f"No auto_trade_book at {path}")
        print("Run Windows research/discovery first, then sync this file to the Mac.")
        return 1
    book = json.loads(path.read_text(encoding="utf-8"))
    print(f"# Auto-trade book  date={book.get('trading_date')}  host={book.get('source_host')}")
    print(f"regime={book.get('regime')} stay_in_cash={book.get('stay_in_cash')} entries={book.get('entry_count')}")
    print(f"generated_at={book.get('generated_at')}")
    print()
    if book.get("stay_in_cash") or not book.get("entries"):
        print("NO ENTER — cash / empty book")
        if book.get("cash_reason"):
            print(book["cash_reason"][:300])
        return 0
    for i, e in enumerate(book.get("entries") or [], 1):
        print(
            f"{i}. ENTER {e.get('symbol')} {e.get('side')} {e.get('strategy')} "
            f"grade={e.get('setup_grade')} setup={e.get('setup_id')}"
        )
        print(
            f"   entry={e.get('entry')} stop={e.get('stop')} target={e.get('target')} "
            f"risk$={e.get('max_risk_dollars')} conf={e.get('confidence')} "
            f"fund={e.get('fundamental_score')} quality={e.get('quality_score')}"
        )
        print(
            f"   checklist={e.get('checklist_passed')} edge={e.get('edge_complete')} "
            f"exp={e.get('expiration')}"
        )
        if e.get("thesis"):
            print(f"   thesis: {str(e['thesis'])[:160]}")
        print()
    print("Watchlist:", ", ".join(book.get("watchlist") or []))
    print()
    print("Mac next: validate vs TOS chain → size by max_risk_* → bracket order → update positions.json + journal")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
