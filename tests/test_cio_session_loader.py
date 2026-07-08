"""Tests for CIO inputs loaded from session directory."""

from __future__ import annotations

from pathlib import Path

from trading_agent.cio.loader import load_from_session_dir
from trading_agent.session.cio_snapshot import save_cio_approval_snapshot
from trading_agent.config import AgentConfig
from trading_agent.pipeline import run_pipeline
from trading_agent.performance.config import PerformanceConfig
from trading_agent.performance.pipeline import run_performance_pipeline
from trading_agent.session.context import save_performance_report


def test_cio_approval_and_review_load_from_session_dir(tmp_path: Path):
    plan = run_pipeline(AgentConfig(fixture_mode=True, use_live_data=False))
    save_cio_approval_snapshot(tmp_path, plan, fixture_mode=True)

    approval_candidates, approval_ctx = load_from_session_dir(tmp_path, mode="approval")
    assert approval_candidates
    assert approval_ctx.overall_market_bias

    perf = run_performance_pipeline(PerformanceConfig(fixture_mode=True))
    save_performance_report(perf, tmp_path)
    flags_path = tmp_path / "intraday_flags.json"
    flags_path.write_text('{"NVDA": "Hold"}', encoding="utf-8")

    _, review_ctx = load_from_session_dir(tmp_path, mode="review")
    assert review_ctx.performance_notes
    assert review_ctx.intraday_flags.get("NVDA") == "Hold"