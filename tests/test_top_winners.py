"""Unit tests for top-winners L1–L4 playbook (offline)."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from trading_agent.odte.top_winners import (
    TopWinnersConfig,
    apply_bracket_preset,
    entry_time_et,
    entry_window_end_et,
    evaluate_entry,
    evaluate_session_window,
    evaluate_ta_gate,
    find_pullback_entry,
    load_top_winner_symbols,
    passes_drop_fast_filter,
    select_entries_for_day,
    simulate_premium_path_l3,
    symbols_from_gap_book,
)

ET = ZoneInfo("America/New_York")


def test_config_l1_l4_defaults():
    cfg = TopWinnersConfig()
    assert cfg.list_size == 10
    assert cfg.monitor_top_n == 2
    assert cfg.entry_mode == "pullback"
    assert cfg.rank_at_decision is True
    assert cfg.take_profit_pct == pytest.approx(0.30)
    assert cfg.stop_loss_pct == pytest.approx(0.25)
    assert cfg.use_trail is True
    assert cfg.max_gap_pct == pytest.approx(8.0)
    assert entry_time_et(cfg).hour == 10
    assert entry_window_end_et(cfg).hour == 10
    assert entry_window_end_et(cfg).minute == 30


def test_bracket_presets():
    cfg = apply_bracket_preset(TopWinnersConfig(), "legacy30_25")
    assert cfg.take_profit_pct == pytest.approx(0.30)
    assert cfg.stop_loss_pct == pytest.approx(0.25)
    cfg = apply_bracket_preset(TopWinnersConfig(), "wr20_15")
    assert cfg.take_profit_pct == pytest.approx(0.20)
    assert cfg.stop_loss_pct == pytest.approx(0.15)


def test_drop_fast_green_passes():
    ev = passes_drop_fast_filter(100.0, 100.6, 100.5)
    assert ev.passed


def test_drop_fast_red_fails():
    ev = passes_drop_fast_filter(100.0, 100.5, 99.0)
    assert not ev.passed
    assert any("red vs open" in r for r in ev.reasons)


def test_drop_fast_dump_fails():
    ev = passes_drop_fast_filter(100.0, 102.0, 100.5)
    assert not ev.passed
    assert any("drop-fast" in r for r in ev.reasons)


def test_drop_fast_weak_fails():
    ev = passes_drop_fast_filter(100.0, 100.1, 100.05)
    assert not ev.passed
    assert any("weak vs open" in r for r in ev.reasons)


def test_symbols_from_gap_book_prefers_up_ranked():
    book = {
        "candidates": [
            {"symbol": "AAA", "direction": "down", "gap_pct": -3.0, "rank_score": 99},
            {"symbol": "BBB", "direction": "up", "gap_pct": 2.0, "rank_score": 50},
            {"symbol": "CCC", "direction": "up", "gap_pct": 5.0, "rank_score": 80},
            {"symbol": "EEE", "direction": "up", "gap_pct": 4.0, "rank_score": 80},
        ]
    }
    syms = symbols_from_gap_book(book, list_size=10)
    assert "AAA" not in syms
    assert syms[0] == "CCC"


def test_load_top_winner_cli_override():
    syms, src = load_top_winner_symbols(
        list_size=10, symbols_override=["nvda", "amd", "tsla", "nvda"]
    )
    assert src == "cli_override"
    assert syms == ["NVDA", "AMD", "TSLA"]


def _synthetic_day_df(*, open_px: float, high_px: float, path_closes: list[float]) -> pd.DataFrame:
    start = datetime(2026, 7, 15, 9, 30, tzinfo=ET)
    closes = path_closes
    n = max(len(closes), 48)
    if len(closes) < n:
        closes = closes + [closes[-1]] * (n - len(closes))
    rows = []
    for i, c in enumerate(closes):
        o = open_px if i == 0 else closes[i - 1]
        h = max(o, c, high_px if i < 10 else c)
        l = min(o, c)
        rows.append({"Open": o, "High": h, "Low": l, "Close": c, "Volume": 1000 + i * 20})
    idx = [start + timedelta(minutes=i) for i in range(len(closes))]
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx))


def test_evaluate_session_window_continue_up():
    closes = [100.0 + i * 0.03 for i in range(36)]
    df = _synthetic_day_df(open_px=100.0, high_px=101.05, path_closes=closes)
    for i, c in enumerate(closes):
        df.iloc[i, df.columns.get_loc("High")] = max(c, closes[max(0, i - 1)]) + 0.02
    ev = evaluate_session_window(df)
    assert ev.passed, ev.reasons


def test_l3_premium_path_tp_and_time():
    # CALL: rise enough for +25% with delta 0.55 → need +0.25/0.55 ≈ 0.45 underlying
    entry = 100.0
    highs = [100.2, 100.6, 100.8]
    lows = [99.9, 100.1, 100.2]
    closes = [100.1, 100.5, 100.7]
    times = [
        datetime(2026, 7, 15, 10, 5, tzinfo=ET),
        datetime(2026, 7, 15, 10, 10, tzinfo=ET),
        datetime(2026, 7, 15, 10, 15, tzinfo=ET),
    ]
    ep, spot, reason, _ = simulate_premium_path_l3(
        "CALL",
        entry,
        highs,
        lows,
        closes,
        times,
        entry_prem=1.0,
        tp_pct=0.20,
        sl_pct=0.15,
        delta=0.55,
        time_exit_et=time(11, 30),
        use_trail=False,
    )
    assert reason in ("take_profit", "time_exit", "trail_exit")
    assert ep > 0


def test_l3_time_exit():
    entry = 100.0
    highs = [100.1, 100.1]
    lows = [99.9, 99.9]
    closes = [100.0, 100.05]
    times = [
        datetime(2026, 7, 15, 11, 30, tzinfo=ET),
        datetime(2026, 7, 15, 11, 35, tzinfo=ET),
    ]
    ep, spot, reason, _ = simulate_premium_path_l3(
        "CALL",
        entry,
        highs,
        lows,
        closes,
        times,
        entry_prem=1.0,
        tp_pct=0.30,
        sl_pct=0.25,
        delta=0.55,
        time_exit_et=time(11, 30),
        use_trail=False,
    )
    assert reason == "time_exit"


def test_select_entries_prefer_single_perfect():
    from trading_agent.odte.top_winners import EntryEvaluation, TaEvaluation

    def mk(sym, q, score):
        ta = TaEvaluation(passed=True, quality_score=q, hard_pass=True)
        e = EntryEvaluation(passed=True, ta=ta, continuation_score=score, gap_pct=2.0, rvol=1.5)
        return (sym, score, 2.0, e)

    ranked = [mk("AAA", 4, 5.0), mk("BBB", 4, 4.0), mk("CCC", 3, 6.0)]
    cfg = TopWinnersConfig(prefer_single_if_perfect=True, max_entries_per_day=2)
    sel = select_entries_for_day(ranked, cfg=cfg)
    assert len(sel) == 1
    assert sel[0][1] == "AAA"


def test_select_entries_second_needs_4of4():
    from trading_agent.odte.top_winners import EntryEvaluation, TaEvaluation

    def mk(sym, q, score):
        ta = TaEvaluation(passed=True, quality_score=q, hard_pass=True)
        e = EntryEvaluation(passed=True, ta=ta, continuation_score=score, gap_pct=2.0, rvol=1.5)
        return (sym, score, 2.0, e)

    ranked = [mk("AAA", 3, 5.0), mk("BBB", 3, 4.0)]
    cfg = TopWinnersConfig(
        prefer_single_if_perfect=False,
        require_quality_4of4_for_second=True,
        max_entries_per_day=2,
    )
    sel = select_entries_for_day(ranked, cfg=cfg)
    # First can enter with q=3; second blocked without 4/4
    assert len(sel) == 1


def test_find_pullback_clock_mode():
    closes = [100.0 + i * 0.02 for i in range(60)]
    df = _synthetic_day_df(open_px=100.0, high_px=101.0, path_closes=closes)
    cfg = TopWinnersConfig(entry_mode="clock")
    fill = find_pullback_entry(df, cfg=cfg)
    assert fill is not None
    assert fill[2] == "clock"


def test_exhaustion_gap_fails_entry():
    closes = [100.0 + i * 0.05 for i in range(40)]
    df = _synthetic_day_df(open_px=100.0, high_px=102.0, path_closes=closes)
    for i, c in enumerate(closes):
        df.iloc[i, df.columns.get_loc("High")] = c + 0.05
        df.iloc[i, df.columns.get_loc("Volume")] = 5000
    # Huge gap vs prior — evaluate_entry with gap_pct high
    e = evaluate_entry(df, cfg=TopWinnersConfig(max_gap_pct=8.0), gap_pct=12.0)
    assert not e.passed
    assert any("exhaustion gap" in r for r in e.reasons)
