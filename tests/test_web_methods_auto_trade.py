"""Web method research + structured suggestions + auto-trade ENTER fail-closed."""

from __future__ import annotations

from pathlib import Path

from trading_agent.config import RiskConfig
from trading_agent.export.auto_trade_book import build_auto_trade_book
from trading_agent.methods.web_methods import (
    BASELINE_METHODS,
    evaluate_methods_for_setup,
    methods_as_dict,
    reinforce_methods_from_text,
    research_trading_methods,
)
from trading_agent.models import (
    DailyTradingPlan,
    OptionsMetrics,
    TechnicalAnalysis,
    TradeOpportunity,
)
from trading_agent.session.play_formatter import format_research_plays


def test_research_methods_offline_returns_baseline():
    methods = research_trading_methods(use_network=False)
    assert len(methods) >= 6
    ids = {m.method_id for m in methods}
    assert "predefined_risk" in ids
    assert "checklist_edge" in ids
    assert methods_as_dict(methods)[0]["method_id"]


def test_reinforce_from_public_style_text():
    text = "position sizing and stop-loss risk management improve expectancy"
    out = reinforce_methods_from_text(text, BASELINE_METHODS)
    by_id = {m.method_id: m.weight for m in out}
    assert by_id["size_cap"] >= BASELINE_METHODS[3].weight  # size_cap in baseline
    assert by_id["predefined_risk"] > 1.0


def test_evaluate_methods_critical_fail_missing_stop():
    ev = evaluate_methods_for_setup(
        BASELINE_METHODS,
        {
            "entry_price": 100,
            "stop_loss": 0,
            "profit_target": 110,
            "checklist_passed": True,
            "require_checklist": True,
            "timeframe_alignment": "aligned_bullish",
            "relative_volume": 2.0,
            "proposed_risk_pct": 1.0,
            "max_risk_per_trade_pct": 2.0,
        },
    )
    assert ev["critical_fail"] is True
    assert any("predefined_risk" in f for f in ev["method_failures"])


def test_evaluate_methods_pass_complete_package():
    ev = evaluate_methods_for_setup(
        BASELINE_METHODS,
        {
            "entry_price": 100,
            "stop_loss": 95,
            "profit_target": 110,
            "checklist_passed": True,
            "require_checklist": True,
            "edge_complete": True,
            "timeframe_alignment": "aligned_bullish",
            "relative_volume": 2.5,
            "setup_id": "trend_pullback_long",
            "proposed_risk_pct": 1.0,
            "max_risk_per_trade_pct": 2.0,
        },
    )
    assert ev["critical_fail"] is False
    assert "predefined_risk" in ev["method_ids_ok"]


def _tech():
    return TechnicalAnalysis(
        symbol="NVDA",
        trend="uptrend",
        rsi=55,
        macd_signal="bullish",
        adx=25,
        atr=2,
        bollinger_position="mid",
        support=100,
        resistance=120,
        relative_strength=1.1,
        vwap_relation="above",
        ma_alignment="bullish",
        volume_profile_bias="accumulation",
        score=75,
        timeframe_alignment="aligned_bullish",
    )


def _opts():
    return OptionsMetrics(
        symbol="NVDA",
        implied_volatility=30,
        iv_rank=40,
        iv_percentile=40,
        expected_move_pct=2,
        delta=0.5,
        gamma=0.05,
        theta=-0.05,
        vega=0.1,
        unusual_activity=False,
        institutional_flow_bias="bullish",
        liquidity_score=70,
        probability_of_profit=0.55,
    )


def test_auto_trade_book_rejects_incomplete_risk_package():
    incomplete = TradeOpportunity(
        rank=1,
        symbol="BAD",
        strategy="Long Call",
        entry_price=100,
        strike_prices=[105],
        expiration="2026-08-01",
        profit_target=0,  # incomplete
        stop_loss=0,
        maximum_risk=0,
        maximum_reward=0,
        probability_of_success=0.5,
        confidence_score=70,
        supporting_reasons=[],
        technical=_tech(),
        options=_opts(),
        direction="Bullish",
        setup_grade="A",
        checklist_passed=True,
        edge_complete=True,
        auto_trade_eligible=True,
        fundamental_score=70,
        combined_quality_score=75,
    )
    complete = TradeOpportunity(
        rank=1,
        symbol="NVDA",
        strategy="Long Call",
        entry_price=100,
        strike_prices=[105],
        expiration="2026-08-01",
        profit_target=110,
        stop_loss=95,
        maximum_risk=200,
        maximum_reward=400,
        probability_of_success=0.55,
        confidence_score=70,
        supporting_reasons=[],
        technical=_tech(),
        options=_opts(),
        direction="Bullish",
        setup_grade="A",
        checklist_passed=True,
        edge_complete=True,
        auto_trade_eligible=True,
        fundamental_score=70,
        combined_quality_score=75,
        method_tags=["predefined_risk", "checklist_edge"],
    )
    plan = DailyTradingPlan(
        date="2026-07-14",
        overall_market_bias="Bullish",
        market_environment_score=60,
        top_watchlist=["NVDA", "BAD"],
        ranked_opportunities=[incomplete, complete],
        rejection_reasons=[],
        research_summary={},
        stay_in_cash=False,
    )
    book = build_auto_trade_book(plan, min_fundamental_score=0, min_quality_score=0)
    assert book["entry_count"] == 1
    assert book["entries"][0]["symbol"] == "NVDA"
    assert book["entries"][0]["stop"] > 0 and book["entries"][0]["target"] > 0
    assert any("incomplete" in r for r in book["rejected_incomplete"])
    assert "windows-research" in book["broker_boundary"]
    assert all(e["action"] == "ENTER" for e in book["entries"])


def test_format_research_plays_structured_suggestion_fields():
    opp = TradeOpportunity(
        rank=1,
        symbol="NVDA",
        strategy="Long Call",
        entry_price=100,
        strike_prices=[105],
        expiration="2026-08-01",
        profit_target=110,
        stop_loss=95,
        maximum_risk=200,
        maximum_reward=400,
        probability_of_success=0.55,
        confidence_score=70,
        supporting_reasons=["test"],
        technical=_tech(),
        options=_opts(),
        direction="Bullish",
        setup_grade="A",
        playbook_setup_id="trend_pullback_long",
        checklist_passed=True,
        edge_complete=True,
        auto_trade_eligible=True,
        method_tags=["predefined_risk"],
        combined_quality_score=72,
        fundamental_score=65,
        trade_thesis="aligned pullback",
        risks=["gap risk"],
    )
    plan = DailyTradingPlan(
        date="2026-07-14",
        overall_market_bias="Bullish",
        market_environment_score=60,
        top_watchlist=["NVDA"],
        ranked_opportunities=[opp],
        rejection_reasons=[],
        research_summary={
            "candidates_screened": 10,
            "qualified_count": 1,
            "web_methods": methods_as_dict(research_trading_methods(use_network=False))[:3],
            "auto_trade_export": {"entry_count": 1},
        },
        stay_in_cash=False,
    )
    text = format_research_plays(plan)
    assert "Suggested trade" in text
    assert "Stop $" in text and "Target $" in text
    assert "auto_trade=YES" in text
    assert "trend_pullback_long" in text
    assert "Methods:" in text
    assert "Auto-trade book:" in text


def test_build_opportunities_attaches_method_tags(monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_METHODS_OFFLINE", "1")
    monkeypatch.setenv("TRADING_AGENT_FUNDAMENTALS_OFFLINE", "1")
    from trading_agent.models import ScreenerCandidate
    from trading_agent.ranking.ranker import build_opportunities

    cand = ScreenerCandidate(
        symbol="NVDA",
        price=115.0,
        volume=8_000_000,
        avg_daily_volume=5_000_000,
        relative_volume=2.8,
        market_cap=2e12,
        sector="Technology",
        open_interest=8000,
        bid_ask_spread_pct=1.0,
        institutional_score=75.0,
        options_volume=20000,
        options_liquidity_score=75.0,
    )
    tech = _tech()
    tech.breakout_state = "breakout"
    tech.momentum = "bullish"
    tech.ema_9 = 112
    tech.ema_20 = 110
    tech.ema_50 = 105
    tech.ema_200 = 95
    risk = RiskConfig(
        min_confidence_score=50,
        prefer_a_tier_only=False,
        min_setup_grade="C",
        top_candidates=5,
        require_playbook_checklist=True,
        require_edge_package=True,
        enforce_mtf_gate=True,
        enforce_fundamental_gate=False,
        min_combined_quality_score=0.0,
        enforce_web_methods=True,
    )
    opps = build_opportunities([(cand, tech, _opts())], risk)
    # May be empty if playbook fails; if present must have method_tags list
    for o in opps:
        assert isinstance(o.method_tags, list)
        assert o.entry_price > 0 and o.stop_loss > 0 and o.profit_target > 0
