#!/usr/bin/env python3
"""macOS helper: print options ENTER checklist from auto_trade_book.json.

Does not place orders. Prefer a book generated on this Mac after local research,
or a path you pass explicitly. Work and home stay file-separated.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if path is None:
        sync = os.getenv("TRADING_AGENT_SYNC_DIR", "").strip()
        candidates = []
        if sync:
            candidates.append(Path(sync) / "auto_trade_book.json")
        candidates.append(Path.home() / ".trading_agent" / "sync" / "auto_trade_book.json")
        from datetime import date

        candidates.append(
            Path.home()
            / ".trading_agent"
            / "sessions"
            / date.today().isoformat()
            / "auto_trade_book.json"
        )
        path = next((p for p in candidates if p.exists()), candidates[0])

    if not path.exists():
        print(f"No auto_trade_book at {path}")
        print("Home: run local research or pass an explicit path.")
        print("Work Discord = brief only; do not expect work blotter files here.")
        return 1

    book = json.loads(path.read_text(encoding="utf-8"))
    print(f"# Options auto-trade book  date={book.get('trading_date')}  host={book.get('source_host')}")
    print(
        f"regime={book.get('regime')} stay_in_cash={book.get('stay_in_cash')} "
        f"entries={book.get('entry_count')} instrument_focus=options"
    )
    print(f"generated_at={book.get('generated_at')}")
    print(f"boundary={book.get('broker_boundary', 'n/a')}")
    print()
    if book.get("stay_in_cash") or not book.get("entries"):
        print("NO ENTER — cash / empty book")
        if book.get("cash_reason"):
            print(book["cash_reason"][:400])
        if book.get("rejected_incomplete"):
            print("rejected_incomplete:", book["rejected_incomplete"][:8])
        return 0

    for i, e in enumerate(book.get("entries") or [], 1):
        strikes = e.get("strike_prices") or []
        strike_s = ", ".join(str(s) for s in strikes[:4])
        print(
            f"{i}. ENTER {e.get('symbol')} | {e.get('strategy')} | {e.get('side')} | "
            f"grade={e.get('setup_grade')} | class={e.get('options_strategy_class')}"
        )
        print(
            f"   setup={e.get('setup_id')} | strikes=[{strike_s}] | exp={e.get('expiration')} "
            f"| DTE={e.get('dte')}"
        )
        print(
            f"   IVR={e.get('iv_rank')} POP={e.get('pop')} delta={e.get('delta')} "
            f"defined_risk={e.get('defined_risk')} instrument={e.get('instrument')}"
        )
        print(
            f"   entry={e.get('entry')} stop={e.get('stop')} target={e.get('target')} "
            f"max_risk$={e.get('max_risk_dollars')} conf={e.get('confidence')}"
        )
        print(
            f"   checklist={e.get('checklist_passed')} edge={e.get('edge_complete')} "
            f"methods={e.get('method_tags')}"
        )
        if e.get("thesis"):
            print(f"   thesis: {str(e['thesis'])[:160]}")
        print()
    print("Watchlist:", ", ".join(book.get("watchlist") or []))
    print()
    print("TOS next: open chain → match strikes/DTE → defined-risk bracket → size by max_risk$")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
