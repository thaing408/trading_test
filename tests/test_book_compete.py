"""Books compete for ticker — score mode helpers."""

from __future__ import annotations

from trading_agent.discipline.compete import (
    annotate_entry_compete,
    book_gates_mode,
    compute_compete_score,
    is_safety_block,
    prefer_entry_by_compete,
    score_gate_results,
    should_hard_reject_books,
)
from trading_agent.discipline.ta_books import TaGateResult


def test_book_gates_mode_env(monkeypatch):
    monkeypatch.delenv("TRADING_AGENT_BOOK_GATES_MODE", raising=False)
    assert book_gates_mode() == "hard"
    monkeypatch.setenv("TRADING_AGENT_BOOK_GATES_MODE", "score")
    assert book_gates_mode() == "score"


def test_score_dedupes_mechanism():
    rows = [
        TaGateResult(ok=True, book="A", mechanism="murphy_indicator_confluence", reasons=[]),
        TaGateResult(ok=True, book="B", mechanism="murphy_indicator_confluence", reasons=[]),
        TaGateResult(ok=False, book="C", mechanism="oneil_can_slim_proxy", reasons=["rvol"]),
        TaGateResult(
            ok=True,
            book="D",
            mechanism="dalton_value_area",
            reasons=["inactive — missing profile"],
        ),
    ]
    pts, by_mech = score_gate_results(rows)
    assert by_mech["murphy_indicator_confluence"] == 1.0
    assert by_mech["oneil_can_slim_proxy"] == 0.0
    assert by_mech["dalton_value_area"] == 0.0
    assert pts == 1.0


def test_safety_block_bulkowski():
    rows = [
        TaGateResult(
            ok=False,
            book="Bulkowski",
            mechanism="bulkowski_pattern_bias",
            reasons=["opposing H&S"],
        )
    ]
    assert is_safety_block(rows) is True
    assert should_hard_reject_books(mode="score", bundle_ok=False, results=rows) is True
    soft = [
        TaGateResult(
            ok=False,
            book="Minervini",
            mechanism="minervini_vcp_breakout",
            reasons=["no VCP"],
        )
    ]
    assert should_hard_reject_books(mode="score", bundle_ok=False, results=soft) is False
    assert should_hard_reject_books(mode="hard", bundle_ok=False, results=soft) is True


def test_compete_score_math():
    assert compute_compete_score(setup_core=70, book_points=3, method_boost=4) == 77.0


def test_prefer_entry_by_compete_keeps_higher():
    desk = {
        "symbol": "NVDA",
        "quality_score": 80,
        "method_tags": ["desk"],
        "compete_score": 90,
    }
    mm = {
        "symbol": "NVDA",
        "quality_score": 70,
        "method_tags": ["multi_method"],
        "compete_score": 75,
    }
    win = prefer_entry_by_compete(mm, desk)
    assert win["compete_score"] == 90
    assert "desk" in win["method_tags"]
    assert "multi_method" in win["method_tags"]


def test_annotate_entry_compete_fills_missing():
    row = annotate_entry_compete(
        {"symbol": "AAPL", "quality_score": 60, "method_tags": ["a", "b"]}
    )
    assert row["compete_score"] >= 60
