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


def _patch_firm_tools(monkeypatch):
    def fake_call(name, *, symbol, **kwargs):
        from trading_agent.firm.tools import ToolResult

        data = {
            "ohlcv": {"status": "ok", "last": 1.0, "closes": [1.0] * 30,
                      "highs": [1.1] * 30, "lows": [0.9] * 30, "volumes": [1e6] * 30,
                      "change_pct": 0.0, "n": 30},
            "ta_bundle": {
                "status": "ok", "last": 1.0, "rsi14": 50, "macd": "neutral",
                "ma_alignment": "mixed", "bollinger": "middle", "atr14": 1.0,
                "adx14": 20, "support_resistance": [0.9, 1.1], "regime": "range_or_mixed",
                "bias": "neutral", "change_pct": 0.0,
            },
            "news": {"status": "empty", "items": [], "source": "test"},
            "fundamentals": {
                "status": "ok", "score": 55.0, "passed": True, "reasons": ["mid"],
                "pe_ttm": 20, "forward_pe": 18, "market_cap": 1e10,
                "profit_margin": 0.1, "revenue_growth": 0.05, "debt_to_equity": 40,
                "sector": "Tech", "source": "test",
            },
            "insider": {"status": "empty", "items": []},
            "social": {
                "status": "ok", "score": 0, "tilt": "neutral", "peaks": [],
                "engagement_notes": "proxy", "source": "news_tone_proxy",
            },
        }.get(name) or {"status": "empty"}
        return ToolResult(tool=name, ok=True, data=data, stub=False)

    monkeypatch.setattr("trading_agent.firm.runner.call_tool", fake_call)
    monkeypatch.setattr("trading_agent.firm.react.call_tool", fake_call)


def test_firm_force_writes_artifacts(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_AGENT_FIRM", "0")
    monkeypatch.setenv("TRADING_AGENT_FIRM_LLM", "0")
    _patch_firm_tools(monkeypatch)
    out = run_firm_for_symbol(
        "AAPL",
        trading_date="2026-08-17",
        session_root=tmp_path,
        force=True,
        use_llm=False,
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
    assert len(state.react_log) >= 4
    fund = json.loads((d / "fundamental_report.json").read_text())
    assert fund["meta"]["status"] in ("stub", "complete", "empty")
    assert fund["fundamental_score"] == 55.0


def test_firm_sleeve_index(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_AGENT_FIRM", "1")
    monkeypatch.setenv("TRADING_AGENT_FIRM_MAX_SYMBOLS", "2")
    monkeypatch.setenv("TRADING_AGENT_FIRM_LLM", "0")
    _patch_firm_tools(monkeypatch)
    out = run_firm_sleeve(
        ["AAPL", "MSFT", "NVDA"],
        trading_date="2026-08-17",
        session_root=tmp_path,
        use_llm=False,
    )
    assert out.get("ok")
    assert out.get("symbols") == ["AAPL", "MSFT"]
    idx = Path(out["index_path"])
    assert idx.is_file()
    data = json.loads(idx.read_text())
    assert data["symbols"] == ["AAPL", "MSFT"]
    assert data.get("phase") == "P3_trader"

def test_maybe_run_after_research_respects_flag(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_AGENT_FIRM", "0")
    session_dir = tmp_path / "2026-08-17"
    session_dir.mkdir()
    out = maybe_run_firm_after_research(["AAPL"], session_dir=session_dir)
    assert out.get("skipped")


def test_tool_registry_lists_and_unknown():
    tools = list_tools()
    assert any(t["name"] == "ohlcv" for t in tools)
    bad = call_tool("nope", symbol="AAPL")
    assert not bad.ok
    # live gather may succeed or soft-fail; never crash
    r = call_tool("social", symbol="AAPL")
    assert r.tool == "social"
    assert isinstance(r.data, dict)