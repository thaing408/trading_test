"""Tests for systematic 5-step process runbook."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from trading_agent.runbook import process as proc

ET = ZoneInfo("America/New_York")


@pytest.fixture()
def proc_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("TRADING_AGENT_PROCESS_DIR", str(tmp_path / "process"))
    return tmp_path / "process"


def test_regime_and_status_scoring(proc_dir: Path):
    day = date(2026, 8, 7)
    proc.set_regime("trade", regime="bull", reason="SPY above 21 EMA", day=day)
    proc.upsert_focus_list(["NVDA", "AMD", "META"], day=day)
    proc.upsert_trade_card(
        "NVDA",
        trigger="10:00 VWAP reclaim",
        stop="OR low",
        size_risk="0.5R",
        exit_plan="+30% / trail",
        day=day,
    )
    payload = proc.run_process_status(day=day, probe=False)
    assert payload["bias"] == "trade"
    assert payload["overall_score"] > 40
    by_id = {s.step_id: s for s in payload["steps"]}
    assert by_id["read_market"].score >= 80
    assert by_id["select_stocks"].score >= 70
    assert by_id["prepare_trades"].score >= 50


def test_cash_bias_relaxes_prep(proc_dir: Path):
    day = date(2026, 8, 8)
    proc.set_regime("cash", regime="risk-off", reason="stay in cash", day=day)
    steps = proc.score_steps(proc.load_day_state(day), artifacts={}, now=datetime(2026, 8, 8, 10, 0, tzinfo=ET))
    by_id = {s.step_id: s for s in steps}
    assert by_id["prepare_trades"].score >= 80


def test_violation_penalizes_execute(proc_dir: Path):
    day = date(2026, 8, 9)
    proc.set_regime("trade", regime="bull", day=day)
    proc.upsert_trade_card(
        "AAPL",
        trigger="breakout",
        stop="2%",
        size_risk="1R",
        exit_plan="trail",
        day=day,
    )
    before = proc.score_steps(
        proc.load_day_state(day),
        artifacts={},
        now=datetime(2026, 8, 9, 11, 0, tzinfo=ET),
    )
    score_before = {s.step_id: s.score for s in before}["execute_rules"]
    proc.append_violation("moved stop without rule", day=day)
    after = proc.score_steps(
        proc.load_day_state(day),
        artifacts={},
        now=datetime(2026, 8, 9, 11, 0, tzinfo=ET),
    )
    score_after = {s.step_id: s.score for s in after}["execute_rules"]
    assert score_after < score_before


def test_trade_card_complete():
    c = proc.TradeCard(symbol="X", trigger="a", stop="b", size_risk="c", exit_plan="d")
    assert c.is_complete()
    assert not proc.TradeCard(symbol="X", trigger="a").is_complete()


def test_format_report_contains_steps(proc_dir: Path):
    day = date(2026, 8, 10)
    proc.ensure_day_state(day)
    text = proc.format_process_report(proc.run_process_status(day=day, probe=False))
    assert "Read the market" in text
    assert "Select the right stocks" in text
    assert "Prepare every trade" in text
    assert "Execute clear rules" in text
    assert "Review and improve" in text
