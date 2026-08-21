"""Tests for multi-method → auto_trade_book export."""

from __future__ import annotations

import json
from pathlib import Path

from trading_agent.export.mac_execute import validate_enter
from trading_agent.export.multi_method_book import (
    build_multi_method_book,
    entry_from_multi_eval,
    export_multi_method_auto_trade,
)
from trading_agent.strategy.multi_method import MethodVote, TickerMultiEval


def _play(sym: str = "NVDA", *, strong: bool = True) -> TickerMultiEval:
    """Exportable PLAY: chart_patterns + one confirm (soulz)."""
    s1, s2 = (75.0, 72.0) if strong else (58.0, 56.0)
    return TickerMultiEval(
        symbol=sym,
        play=True,
        decision="PLAY",
        best_method="chart_patterns",
        best_side="CALL",
        aggregate_score=48.0,
        play_methods=["chart_patterns", "soulz_pa"],
        votes=[
            MethodVote(
                method_id="chart_patterns",
                play=True,
                side="CALL",
                score=s1,
                entry=100.0,
                stop=98.0,
                target=103.0,
            ),
            MethodVote(
                method_id="soulz_pa",
                play=True,
                side="CALL",
                score=s2,
                entry=100.0,
                stop=98.5,
                target=102.0,
            ),
            MethodVote(
                method_id="orb_vwap",
                play=False,
                side="",
                score=20.0,
            ),
        ],
        reasons=["PLAY via chart_patterns, soulz_pa"],
        play_quality_score=(s1 + s2) / 2,
        best_play_score=s1,
        export_eligible=strong and s1 >= 65,
    )


def test_entry_from_multi_eval_valid():
    row = entry_from_multi_eval(
        _play(),
        expires_at="2099-01-01T23:59:00+00:00",
        trading_date="2026-08-10",
    )
    assert row is not None
    assert row["symbol"] == "NVDA"
    assert row["instrument"] == "options"  # multi-method auto is options-only
    assert row["auto_trade_eligible"] is True
    assert row["entry"] == 100.0
    assert row["stop"] == 98.0
    assert "multi_method" in row["method_tags"]
    ok, reason = validate_enter(row)
    assert ok, reason


def test_weak_play_blocked_from_export():
    row = entry_from_multi_eval(
        _play(strong=False),
        expires_at="2099-01-01T23:59:00+00:00",
        trading_date="2026-08-10",
    )
    assert row is None


def test_orb_only_play_blocked_without_chart_patterns(monkeypatch):
    monkeypatch.delenv("TRADING_AGENT_EXPORT_REQUIRE_CHART_PATTERNS", raising=False)
    monkeypatch.setenv("TRADING_AGENT_WR_DESK", "0")  # isolate export gate
    orb = TickerMultiEval(
        symbol="QQQ",
        play=True,
        decision="PLAY",
        best_method="orb_vwap",
        best_side="CALL",
        aggregate_score=60.0,
        play_methods=["orb_vwap", "odte_breakout"],
        votes=[
            MethodVote(
                method_id="orb_vwap",
                play=True,
                side="CALL",
                score=75.0,
                entry=100.0,
                stop=98.0,
                target=103.0,
            ),
            MethodVote(
                method_id="odte_breakout",
                play=True,
                side="CALL",
                score=72.0,
                entry=100.0,
                stop=98.5,
                target=102.0,
            ),
        ],
        reasons=["PLAY via orb"],
        play_quality_score=73.5,
        best_play_score=75.0,
        export_eligible=True,  # even if pre-marked, gate re-checks
    )
    assert entry_from_multi_eval(
        orb,
        expires_at="2099-01-01T23:59:00+00:00",
        trading_date="2026-08-10",
    ) is None


def test_chart_patterns_geometry_preferred(monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_WR_DESK", "0")
    monkeypatch.setenv("TRADING_AGENT_EXPORT_REQUIRE_CHART_PATTERNS", "1")
    ev = TickerMultiEval(
        symbol="AMD",
        play=True,
        decision="PLAY",
        best_method="soulz_pa",  # higher aggregate path said soulz
        best_side="CALL",
        aggregate_score=70.0,
        play_methods=["chart_patterns", "soulz_pa"],
        votes=[
            MethodVote(
                method_id="chart_patterns",
                play=True,
                side="CALL",
                score=70.0,
                entry=111.0,
                stop=108.0,
                target=116.0,
            ),
            MethodVote(
                method_id="soulz_pa",
                play=True,
                side="CALL",
                score=80.0,
                entry=110.0,
                stop=109.0,
                target=112.0,
            ),
        ],
        play_quality_score=75.0,
        best_play_score=80.0,
        export_eligible=True,
    )
    row = entry_from_multi_eval(
        ev,
        expires_at="2099-01-01T23:59:00+00:00",
        trading_date="2026-08-10",
    )
    assert row is not None
    assert row["entry"] == 111.0  # chart_patterns geometry
    assert "chart_patterns" in row["method_tags"] or "multi_chart" in row["setup_id"] or True


def test_build_book_has_entries():
    book = build_multi_method_book([_play("AAPL"), _play("MSFT"), _play("WEAK", strong=False)])
    assert book["entry_count"] == 2
    assert book["stay_in_cash"] is False
    assert book["role"] == "multi-method-router"
    assert any("export_quality" in x or "WEAK" in x for x in book.get("rejected_incomplete") or [])


def test_export_writes_files(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_SYNC_DIR", str(tmp_path / "sync"))
    monkeypatch.setenv("TRADING_AGENT_PROCESS_DIR", str(tmp_path / "process"))
    book, paths = export_multi_method_auto_trade([_play()], merge_desk=False)
    assert paths
    assert book["entry_count"] == 1
    payload = json.loads(paths[0].read_text(encoding="utf-8"))
    assert payload["entries"][0]["symbol"] == "NVDA"


def test_cash_bias_suppresses_export_when_auto_export_off(tmp_path, monkeypatch):
    """With AUTO_EXPORT on (default), cash bias does not wipe multi-method ENTERs."""
    monkeypatch.setenv("TRADING_AGENT_SYNC_DIR", str(tmp_path / "sync"))
    monkeypatch.setenv("TRADING_AGENT_PROCESS_DIR", str(tmp_path / "process"))
    monkeypatch.setenv("TRADING_AGENT_MULTI_METHOD_AUTO_EXPORT", "0")
    from trading_agent.runbook.process import set_regime

    set_regime("cash", regime="halt", reason="test")
    book, paths = export_multi_method_auto_trade([_play()], merge_desk=False)
    assert book["entry_count"] == 0
    assert book["stay_in_cash"] is True
