"""Manage cadence logging + backtest exit_mode / manage_every_n."""

from __future__ import annotations

from trading_agent.backtest.fills import simulate_directional_exit
from trading_agent.intraday.manage_log import (
    append_manage_event,
    log_interval_decision,
    summarize_manage_log,
)


def test_path_stops_on_intrabar_low():
    # path: low tags stop
    px, reason, held = simulate_directional_exit(
        100.0,
        98.0,
        110.0,
        future_highs=[101, 102],
        future_lows=[97.5, 99],  # bar0 under stop
        future_closes=[100.5, 100],
        bullish=True,
        exit_mode="path",
        manage_every_n_bars=1,
    )
    assert reason == "stop_loss"
    assert held == 1
    assert px == 98.0


def test_close_only_ignores_intrabar_wick():
    # close stayed above stop → no stop on bar0
    px, reason, held = simulate_directional_exit(
        100.0,
        98.0,
        110.0,
        future_highs=[101, 102],
        future_lows=[97.5, 99],
        future_closes=[100.5, 100],  # closes never <= 98
        bullish=True,
        exit_mode="close_only",
        manage_every_n_bars=1,
    )
    assert reason == "time_exit"
    assert held == 2


def test_manage_every_n_skips_bar():
    # bar0 would stop on path, but only check every 2 bars → skip bar0
    px, reason, held = simulate_directional_exit(
        100.0,
        98.0,
        110.0,
        future_highs=[101, 102, 103],
        future_lows=[97.0, 99, 97.5],
        future_closes=[100, 100, 100],
        bullish=True,
        exit_mode="path",
        manage_every_n_bars=2,
    )
    # bar index 1 is 2nd bar → checked; low=99 not stop; bar2 low 97.5 → stop
    assert reason == "stop_loss"
    assert held == 3


def test_manage_log_interval(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_MANAGE_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("TRADING_AGENT_MANAGE_LOG", "1")
    log_interval_decision(
        cycle=1,
        wait_minutes=3,
        baseline_minutes=15,
        in_position_minutes=3,
        has_open_positions=True,
        open_symbols=["QQQ"],
    )
    summary = summarize_manage_log(day=None)
    # day uses utc today; write with explicit path
    from datetime import date

    from trading_agent.intraday.manage_log import manage_log_path

    # force read from what we wrote — append used utc date
    p = manage_log_path()
    assert p.is_file()
    s = summarize_manage_log(path=p)
    assert s["events"] >= 1
    assert s["intervals"].get("in_position_fast", 0) >= 1
