"""P0 firm sleeve: schemas, persistence, flag off = no-op."""

from __future__ import annotations

import json
from pathlib import Path

from trading_agent.firm.roles import FIRM_ROLES, roles_by_team
from trading_agent.firm.runner import (
    maybe_run_firm_after_research,
    run_firm_for_symbol,
    run_firm_sleeve,
)
from trading_agent.firm.state import firm_enabled, firm_symbol_dir, load_symbol_state
from trading_agent.firm.tools import call_tool, list_tools


def test_roles_cover_paper_teams():
    teams = roles_by_team()
    assert "analysts" in teams and len(teams["analysts"]) == 4
    assert "researchers" in teams
    assert "trader" in teams
    assert "risk" in teams
    assert "manager" in teams
    assert "fundamental_analyst" in FIRM_ROLES


def test_firm_disabled_is_noop(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_AGENT_FIRM", "0")
    assert not firm_enabled()
    out = run_firm_for_symbol("AAPL", session_root=tmp_path)
    assert out.get("skipped") is True
    assert not list(tmp_path.rglob("state.json"))


def test_firm_force_writes_artifacts(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_AGENT_FIRM", "0")
    out = run_firm_for_symbol(
        "AAPL", trading_date="2026-08-17", session_root=tmp_path, force=True
    )
    assert out.get("ok") and not out.get("skipped")
    d = firm_symbol_dir("2026-08-17", "AAPL", session_root=tmp_path)
    assert (d / "state.json").is_file()
    assert (d / "fundamental_report.json").is_file()
    assert (d / "debate_verdict.json").is_file()
    assert (d / "firm_card.json").is_file()
    assert (d / "roles.json").is_file()
    state = load_symbol_state("2026-08-17", "AAPL", session_root=tmp_path)
    assert state is not None
    assert state.status == "complete"
    assert len(state.react_log) >= 4  # analyst stub tools
    fund = json.loads((d / "fundamental_report.json").read_text())
    assert fund["meta"]["status"] == "empty"
    assert fund["fundamental_score"] == 0.0


def test_firm_sleeve_index(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_AGENT_FIRM", "1")
    monkeypatch.setenv("TRADING_AGENT_FIRM_MAX_SYMBOLS", "2")
    out = run_firm_sleeve(
        ["AAPL", "MSFT", "NVDA"],
        trading_date="2026-08-17",
        session_root=tmp_path,
    )
    assert out.get("ok")
    assert out.get("symbols") == ["AAPL", "MSFT"]
    idx = Path(out["index_path"])
    assert idx.is_file()
    data = json.loads(idx.read_text())
    assert data["symbols"] == ["AAPL", "MSFT"]


def test_maybe_run_after_research_respects_flag(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_AGENT_FIRM", "0")
    session_dir = tmp_path / "2026-08-17"
    session_dir.mkdir()
    out = maybe_run_firm_after_research(["AAPL"], session_dir=session_dir)
    assert out.get("skipped")


def test_tool_stubs():
    tools = list_tools()
    assert any(t["name"] == "ohlcv" for t in tools)
    r = call_tool("ohlcv", symbol="AAPL")
    assert r.ok and r.stub
    bad = call_tool("nope", symbol="AAPL")
    assert not bad.ok
