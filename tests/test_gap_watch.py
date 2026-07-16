"""Gap book file watch + new-continuation detection."""

from __future__ import annotations

import json
import time
from pathlib import Path

from trading_agent.export.gap_watch import (
    check_and_process_gap_book,
    inspect_gap_book_changes,
    load_watch_state,
    save_watch_state,
)


def _write_book(path: Path, symbols: list[str], *, state: str = "continuation") -> None:
    cont = [
        {
            "symbol": s,
            "state": state,
            "direction": "up",
            "gap_pct": 2.0,
            "gap_date": "2026-07-10",
            "days_since_gap": 5,
            "continuation_bias": "long",
        }
        for s in symbols
    ]
    book = {
        "as_of": "2026-07-16T00:00:00+00:00",
        "candidates": cont,
        "continuation": cont if state == "continuation" else [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(book), encoding="utf-8")


def test_detects_new_continuation(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_SYNC_DIR", str(tmp_path))
    book_path = tmp_path / "gap_screener_book.json"
    monkeypatch.setattr(
        "trading_agent.export.gap_watch.gap_book_paths",
        lambda: [book_path],
    )
    monkeypatch.setattr(
        "trading_agent.export.gap_book.gap_book_paths",
        lambda: [book_path],
    )
    _write_book(book_path, ["AAA", "BBB"])

    snap1 = inspect_gap_book_changes({})
    assert snap1.file_exists
    assert snap1.changed
    assert set(snap1.continuation) == {"AAA", "BBB"}
    assert set(snap1.new_continuation) == {"AAA", "BBB"}

    state = {
        "mtime": snap1.mtime,
        "content_hash": snap1.content_hash,
        "continuation": ["AAA", "BBB"],
        "processed_continuation": ["AAA", "BBB"],
    }
    state_path = tmp_path / "gap_book_watch_state.json"
    save_watch_state(state, state_path)
    snap2 = inspect_gap_book_changes(load_watch_state(state_path))
    assert snap2.changed is False
    assert snap2.new_continuation == []

    time.sleep(0.05)
    _write_book(book_path, ["AAA", "BBB", "CCC"])
    snap3 = inspect_gap_book_changes(load_watch_state(state_path))
    assert snap3.changed is True
    assert "CCC" in snap3.new_continuation

def test_check_and_process_no_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_SYNC_DIR", str(tmp_path))
    # Isolate from real ~/.researcher gap book
    monkeypatch.setattr(
        "trading_agent.export.gap_watch.gap_book_paths",
        lambda: [tmp_path / "gap_screener_book.json"],
    )
    from trading_agent.config import AgentConfig

    res = check_and_process_gap_book(AgentConfig(fixture_mode=True, use_live_data=False))
    assert res.triggered is False
    assert res.snapshot.file_exists is False