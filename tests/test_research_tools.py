"""Hypothesis registry, promotion gate, session replay."""

from __future__ import annotations

import json
from pathlib import Path

from trading_agent.backtest.fills import apply_trade_costs
from trading_agent.research.hypotheses import get_hypothesis, hypothesis_for_setup, list_hypotheses
from trading_agent.research.promotion import PromotionChecklist, evaluate_promotion
from trading_agent.research.replay import format_replay_report, replay_session_candidates


def test_hypotheses_nonempty():
    rows = list_hypotheses()
    assert len(rows) >= 5
    assert get_hypothesis("options_credit_bull_put") is not None
    assert hypothesis_for_setup("options_credit_iron_condor") is not None


def test_promotion_fails_without_evidence():
    result = evaluate_promotion(PromotionChecklist(name="baseline"))
    assert result.approved is False
    assert any("offline_trades" in f for f in result.failures)


def test_promotion_passes_with_full_checklist():
    check = PromotionChecklist(
        name="good",
        offline_trades=40,
        offline_expectancy=50.0,
        offline_win_rate=0.55,
        offline_max_dd=5_000,
        gates_on_ablation_done=True,
        multi_regime_done=True,
        costs_modeled=True,
        paper_days=15,
        paper_trades=20,
        paper_expectancy=10.0,
        human_reviewed=True,
    )
    result = evaluate_promotion(check)
    assert result.approved is True


def test_apply_trade_costs():
    raw = 100.0
    net = apply_trade_costs(raw, risk_dollars=1000.0, commission_per_trade=1.0, slippage_bps=5.0)
    # 5 bps * 2 * 1000 = 1.0 slip + 1 commission
    assert net == 98.0


def test_session_replay(tmp_path: Path):
    session = tmp_path / "2026-08-01"
    session.mkdir()
    (session / "auto_trade_book.json").write_text(
        json.dumps(
            {
                "stay_in_cash": False,
                "entries": [
                    {
                        "symbol": "TSLA",
                        "setup_id": "options_credit_iron_condor",
                        "entry": 250,
                        "stop": 240,
                        "target": 260,
                        "max_risk_dollars": 50,
                        "auto_trade_eligible": True,
                    },
                    {
                        "symbol": "BAD",
                        "entry": 0,
                        "stop": 1,
                        "target": 2,
                        "max_risk_dollars": 10,
                        "auto_trade_eligible": True,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    result = replay_session_candidates(session)
    assert result["candidate_count"] == 2
    assert result["pass_count"] == 1
    assert result["reject_count"] == 1
    text = format_replay_report(result)
    assert "TSLA" in text
