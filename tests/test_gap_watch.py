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
    assert "missing" in (res.discord_message or "").lower()


def test_discord_format_includes_real_filename():
    from trading_agent.export.gap_watch import (
        GapAutoTradePrepResult,
        GapWatchSnapshot,
        format_gap_watch_discord,
    )

    snap = GapWatchSnapshot(
        file_path="/Users/thai/.trading_agent/sync/gap_screener_book.json",
        file_exists=True,
        changed=True,
        continuation=["AAPL", "MSFT", "NVDA"],
        new_continuation=["NVDA"],
    )
    msg = format_gap_watch_discord(
        GapAutoTradePrepResult(triggered=False, snapshot=snap)
    )
    assert "gap_screener_book.json" in msg
    assert "missing" not in msg
    assert "Continuation: **3**" in msg


def test_prepare_preserves_file_path_on_discord(tmp_path: Path, monkeypatch):
    """Regression: prep must not wipe file_path → Discord 'File: missing'."""
    from trading_agent.export.gap_watch import (
        GapWatchSnapshot,
        format_gap_watch_discord,
        prepare_auto_trade_for_symbols,
    )
    from trading_agent.config import AgentConfig

    book_path = tmp_path / "gap_screener_book.json"
    book_path.write_text("{}", encoding="utf-8")
    snap = GapWatchSnapshot(
        file_path=str(book_path),
        file_exists=True,
        changed=True,
        continuation=["AAA", "BBB"],
        new_continuation=["AAA", "BBB"],
    )

    def fake_pipeline(cfg):
        class P:
            ranked_opportunities = []
            stay_in_cash = True
            watchlist = []

        return P()

    monkeypatch.setattr("trading_agent.pipeline.run_pipeline", fake_pipeline)
    monkeypatch.setattr(
        "trading_agent.export.auto_trade_book.export_plan_for_execution",
        lambda plan, session_dir=None: {
            "entries": [],
            "stay_in_cash": True,
            "_written_paths": [str(tmp_path / "auto_trade_book.json")],
        },
    )
    res = prepare_auto_trade_for_symbols(
        ["AAA", "BBB"],
        AgentConfig(fixture_mode=True, use_live_data=False),
        snapshot=snap,
    )
    assert res.snapshot.file_path == str(book_path)
    msg = format_gap_watch_discord(res)
    assert "gap_screener_book.json" in msg
    assert "`missing`" not in msg