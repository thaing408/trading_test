"""Adaptive PT/SL check spacing: faster while open positions exist."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from trading_agent.session.config import SessionConfig
from trading_agent.session.orchestrator import (
    resolve_intraday_wait_minutes,
    run_session,
    session_has_open_positions,
)
from trading_agent.session.schedule import (
    DEFAULT_IN_POSITION_INTERVAL_MINUTES,
    DEFAULT_INTRADAY_INTERVAL_MINUTES,
    next_intraday_interval_minutes,
)


def test_next_intraday_interval_faster_when_in_position():
    baseline = DEFAULT_INTRADAY_INTERVAL_MINUTES  # 15
    flat = next_intraday_interval_minutes(baseline, False)
    open_book = next_intraday_interval_minutes(baseline, True)
    assert flat == baseline
    assert 0 < open_book < flat
    # restore when flat again
    assert next_intraday_interval_minutes(baseline, False) == flat


def test_next_intraday_interval_custom_in_position_minutes():
    assert next_intraday_interval_minutes(15, True, in_position_minutes=5) == 5
    assert next_intraday_interval_minutes(15, True, in_position_minutes=1) == 1
    # fast must stay strictly below baseline when baseline > 1
    assert next_intraday_interval_minutes(15, True, in_position_minutes=20) == 14
    assert next_intraday_interval_minutes(15, False, in_position_minutes=3) == 15


def test_resolve_intraday_wait_minutes_shipped_entry():
    cfg = SessionConfig(
        intraday_interval_minutes=15,
        intraday_in_position_interval_minutes=3,
    )
    flat = resolve_intraday_wait_minutes(cfg, has_open_positions=False)
    with_pos = resolve_intraday_wait_minutes(cfg, has_open_positions=True)
    assert flat == 15
    assert with_pos == 3
    assert 0 < with_pos < flat
    # back to flat
    assert resolve_intraday_wait_minutes(cfg, has_open_positions=False) == 15


def test_session_has_open_positions_from_file(tmp_path: Path):
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"positions": []}), encoding="utf-8")
    filled = tmp_path / "open.json"
    filled.write_text(
        json.dumps(
            {
                "positions": [
                    {
                        "symbol": "QQQ",
                        "strategy": "Long Call",
                        "entry_price": 1.0,
                        "current_price": 1.1,
                        "quantity": 1,
                        "stop_loss": 0.8,
                        "profit_target": 1.5,
                        "strike_prices": [700.0],
                        "expiration": "2026-07-18",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    flat_cfg = SessionConfig(positions_file=str(empty), fixture_mode=False)
    open_cfg = SessionConfig(positions_file=str(filled), fixture_mode=False)
    assert session_has_open_positions(flat_cfg) is False
    assert session_has_open_positions(open_cfg) is True
    assert resolve_intraday_wait_minutes(flat_cfg) == flat_cfg.intraday_interval_minutes
    assert (
        resolve_intraday_wait_minutes(open_cfg)
        == open_cfg.intraday_in_position_interval_minutes
    )


def test_dry_run_logs_shorter_interval_with_positions(tmp_path: Path, capsys):
    """Fixture/dry-run path still resolves wait via shipped helpers and logs it."""
    pos = tmp_path / "positions.json"
    pos.write_text(
        json.dumps(
            {
                "positions": [
                    {
                        "symbol": "NVDA",
                        "strategy": "Long Call",
                        "entry_price": 2.0,
                        "current_price": 2.2,
                        "quantity": 2,
                        "stop_loss": 1.5,
                        "profit_target": 3.0,
                        "strike_prices": [130.0],
                        "expiration": "2026-08-15",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    log_path = tmp_path / "session.log"
    sess_open = tmp_path / "sess_open"
    sess_open.mkdir()
    plan = sess_open / "daily_plan_context.json"
    plan.write_text(
        json.dumps({"top_watchlist": ["QQQ"], "opportunities": []}),
        encoding="utf-8",
    )
    from trading_agent.session.schedule import DeskPhaseKind

    cfg_open = SessionConfig(
        fixture_mode=True,
        dry_run=True,
        trading_date=date(2026, 7, 9),
        intraday_cycles=2,
        wait_for_schedule=False,
        session_dir=sess_open,
        positions_file=str(pos),
        plan_file=str(plan),
        log_file=str(log_path),
        from_phase=DeskPhaseKind.INTRADAY,
        until_phase=DeskPhaseKind.INTRADAY,
        intraday_interval_minutes=15,
        intraday_in_position_interval_minutes=3,
    )

    with log_path.open("w", encoding="utf-8") as log:
        run_session(cfg_open, log=log)

    text = log_path.read_text(encoding="utf-8")
    assert "next_wait_minutes=3" in text
    assert "open_positions=True" in text

    # Flat book → baseline 15
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"positions": []}), encoding="utf-8")
    log_flat = tmp_path / "session_flat.log"
    sess_flat = tmp_path / "sess_flat"
    sess_flat.mkdir()
    plan_flat = sess_flat / "daily_plan_context.json"
    plan_flat.write_text(plan.read_text(encoding="utf-8"), encoding="utf-8")
    cfg_flat = SessionConfig(
        fixture_mode=True,
        dry_run=True,
        trading_date=date(2026, 7, 9),
        intraday_cycles=1,
        wait_for_schedule=False,
        session_dir=sess_flat,
        positions_file=str(empty),
        plan_file=str(plan_flat),
        log_file=str(log_flat),
        from_phase=DeskPhaseKind.INTRADAY,
        until_phase=DeskPhaseKind.INTRADAY,
        intraday_interval_minutes=15,
        intraday_in_position_interval_minutes=3,
    )
    with log_flat.open("w", encoding="utf-8") as log:
        run_session(cfg_flat, log=log)
    flat_text = log_flat.read_text(encoding="utf-8")
    assert "next_wait_minutes=15" in flat_text
    assert "open_positions=False" in flat_text


def test_default_in_position_constant_below_baseline():
    assert DEFAULT_IN_POSITION_INTERVAL_MINUTES < DEFAULT_INTRADAY_INTERVAL_MINUTES
    assert DEFAULT_IN_POSITION_INTERVAL_MINUTES >= 1
