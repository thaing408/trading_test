"""Tests for multi-method ticker router."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from trading_agent.strategy.multi_method import (
    MultiMethodConfig,
    evaluate_ticker_all_methods,
    format_multi_method_report,
)

ET = ZoneInfo("America/New_York")


def _synthetic_df(n: int = 120, trend: float = 0.05) -> pd.DataFrame:
    # Build RTH-like 15m bars over a few days
    start = datetime(2026, 7, 15, 9, 30, tzinfo=ET)
    rows = []
    idx = []
    px = 100.0
    for i in range(n):
        # skip overnight roughly: 26 bars/day 9:30-16:00
        day = i // 26
        bar = i % 26
        ts = start + timedelta(days=day, minutes=15 * bar)
        px = px + trend + np.sin(i / 5) * 0.1
        o, c = px - 0.1, px + 0.1
        h, l = max(o, c) + 0.3, min(o, c) - 0.3
        rows.append({"Open": o, "High": h, "Low": l, "Close": c, "Volume": 10000 + i * 10})
        idx.append(ts)
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx))


def test_all_methods_return_votes():
    df = _synthetic_df()
    cfg = MultiMethodConfig(
        min_method_score=55,
        min_play_methods=1,
        use_htf_bias=False,
        enabled_methods=(
            "soulz_pa",
            "top_winners",
            "orb_vwap",
            "odte_breakout",
            "fvg",
            "range_fade",
            "sweep",
            "chart_patterns",
            "process_methods",
        ),
    )
    result = evaluate_ticker_all_methods("TEST", cfg=cfg, df=df)
    ids = {v.method_id for v in result.votes}
    for mid in (
        "soulz_pa",
        "top_winners",
        "orb_vwap",
        "odte_breakout",
        "fvg",
        "range_fade",
        "sweep",
        "chart_patterns",
        "process_methods",
    ):
        assert mid in ids
    assert result.decision in ("PLAY", "SKIP", "CONFLICT", "NO_DATA")
    assert 0 <= result.aggregate_score <= 100


def test_process_methods_cannot_unlock_alone():
    df = _synthetic_df(trend=0.0)
    cfg = MultiMethodConfig(
        min_method_score=1.0,  # everything "plays" if scored high
        min_play_methods=1,
        enabled_methods=("process_methods",),
    )
    # only process_methods enabled — should SKIP (cannot unlock)
    result = evaluate_ticker_all_methods("TEST", cfg=cfg, df=df)
    assert result.play is False
    assert result.decision == "SKIP"


def test_passes_export_quality_gate():
    from trading_agent.strategy.multi_method import (
        MethodVote,
        MultiMethodConfig,
        TickerMultiEval,
        passes_export_quality,
    )

    strong = TickerMultiEval(
        symbol="X",
        play=True,
        decision="PLAY",
        best_method="chart_patterns",
        best_side="CALL",
        aggregate_score=45.0,
        play_methods=["chart_patterns", "fvg"],
        votes=[
            MethodVote("chart_patterns", True, "CALL", 75),
            MethodVote("fvg", True, "CALL", 70),
            MethodVote("soulz_pa", False, "", 20),
        ],
        play_quality_score=72.5,
        best_play_score=75,
    )
    ok, why = passes_export_quality(strong)
    assert ok, why

    no_chart = TickerMultiEval(
        symbol="Z",
        play=True,
        decision="PLAY",
        best_method="orb_vwap",
        best_side="CALL",
        aggregate_score=60.0,
        play_methods=["orb_vwap", "odte_breakout"],
        votes=[
            MethodVote("orb_vwap", True, "CALL", 75),
            MethodVote("odte_breakout", True, "CALL", 72),
        ],
        play_quality_score=73.5,
        best_play_score=75,
    )
    ok_nc, why_nc = passes_export_quality(no_chart)
    assert not ok_nc
    assert "chart_patterns" in why_nc

    weak = TickerMultiEval(
        symbol="Y",
        play=True,
        decision="PLAY",
        best_method="chart_patterns",
        best_side="CALL",
        aggregate_score=40.0,
        play_methods=["chart_patterns", "fvg"],
        votes=[
            MethodVote("chart_patterns", True, "CALL", 58),
            MethodVote("fvg", True, "CALL", 56),
        ],
        play_quality_score=57.0,
        best_play_score=58,
    )
    ok2, why2 = passes_export_quality(weak)
    assert not ok2
    assert "weak" in why2 or "58" in why2


def test_format_report():
    df = _synthetic_df()
    r = evaluate_ticker_all_methods("TEST", cfg=MultiMethodConfig(), df=df)
    text = format_multi_method_report([r])
    assert "Multi-Method" in text
    assert "TEST" in text
    assert "soulz_pa" in text


def test_write_process_cards_for_plays(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_PROCESS_DIR", str(tmp_path / "process"))
    from trading_agent.runbook.process import load_day_state
    from trading_agent.strategy.multi_method import (
        MethodVote,
        TickerMultiEval,
        write_process_cards_for_plays,
    )

    play = TickerMultiEval(
        symbol="NVDA",
        play=True,
        decision="PLAY",
        best_method="orb_vwap",
        best_side="CALL",
        aggregate_score=70.0,
        play_methods=["orb_vwap", "odte_breakout"],
        votes=[
            MethodVote(
                method_id="orb_vwap",
                play=True,
                side="CALL",
                score=75,
                entry=100.0,
                stop=98.0,
                target=103.0,
                tags=["or_break_up"],
            ),
            MethodVote(
                method_id="odte_breakout",
                play=True,
                side="CALL",
                score=72,
                entry=100.0,
                stop=98.5,
                target=102.0,
            ),
        ],
        reasons=["PLAY via orb_vwap"],
    )
    skip = TickerMultiEval(
        symbol="SKIPME",
        play=False,
        decision="SKIP",
        best_method="soulz_pa",
        best_side="",
        aggregate_score=20.0,
        votes=[],
        reasons=["no method"],
    )
    writes = write_process_cards_for_plays([play, skip], update_focus=True)
    assert len(writes) == 1
    assert writes[0].written and writes[0].symbol == "NVDA"
    state = load_day_state()
    assert "NVDA" in state.focus_list
    cards = [c for c in state.trade_cards if c.get("symbol") == "NVDA"]
    assert len(cards) == 1
    assert cards[0].get("prepared") is True
    assert "orb_vwap" in cards[0].get("trigger", "")
