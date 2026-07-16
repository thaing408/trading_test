"""Gap screener handoff loader for auto-trade boosts."""

from __future__ import annotations

import json
from pathlib import Path

from trading_agent.export.gap_book import (
    apply_gap_boost_to_opportunity_fields,
    continuation_symbols,
    load_gap_book,
)


def test_load_and_continuation(tmp_path: Path, monkeypatch):
    book = {
        "candidates": [
            {
                "symbol": "IBM",
                "state": "continuation",
                "direction": "up",
                "gap_pct": 2.5,
                "gap_date": "2026-07-10",
                "days_since_gap": 5,
                "continuation_bias": "long",
            },
            {
                "symbol": "AAPL",
                "state": "full_fill",
                "direction": "up",
                "gap_pct": 1.2,
                "gap_date": "2026-07-12",
                "days_since_gap": 2,
                "continuation_bias": "none",
            },
        ],
        "continuation": [
            {
                "symbol": "IBM",
                "state": "continuation",
                "direction": "up",
                "gap_pct": 2.5,
                "gap_date": "2026-07-10",
                "days_since_gap": 5,
                "continuation_bias": "long",
            }
        ],
    }
    path = tmp_path / "gap_screener_book.json"
    path.write_text(json.dumps(book), encoding="utf-8")
    monkeypatch.setenv("TRADING_AGENT_SYNC_DIR", str(tmp_path))

    loaded = load_gap_book()
    assert continuation_symbols(loaded) == {"IBM"}
    tags, elig, note = apply_gap_boost_to_opportunity_fields(
        symbol="IBM",
        method_tags=[],
        auto_trade_eligible=True,
        book=loaded,
    )
    assert "gap_continuation_4d" in tags
    assert "continuation" in note.lower() or "Unfilled" in note or "gap" in note.lower()
    tags2, _, note2 = apply_gap_boost_to_opportunity_fields(
        symbol="AAPL",
        method_tags=[],
        auto_trade_eligible=True,
        book=loaded,
    )
    assert "gap_filled" in tags2
