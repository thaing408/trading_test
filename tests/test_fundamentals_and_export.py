"""Fundamentals scoring + auto_trade_book export (Windows research → Mac)."""

from __future__ import annotations

from pathlib import Path

from trading_agent.export.auto_trade_book import (
    build_auto_trade_book,
    export_plan_for_execution,
)
from trading_agent.fundamentals.quality import (
    combine_quality_score,
    score_fundamentals_from_info,
)
from trading_agent.journal.trades import JournalTrade, append_journal_trade, load_journal_trades
from trading_agent.models import (
    DailyTradingPlan,
    OptionsMetrics,
    TechnicalAnalysis,
    TradeOpportunity,
)


def test_fundamental_score_rewards_quality():
    strong = score_fundamentals_from_info(
        "NVDA",
        {
            "marketCap": 2e12,
            "trailingPE": 40,
            "forwardPE": 28,
            "profitMargins": 0.25,
            "revenueGrowth": 0.3,
            "debtToEquity": 40,
        },
        min_score=45,
    )
    weak = score_fundamentals_from_info(
        "JUNK",
        {
            "marketCap": 5e8,
            "trailingPE": -5,
            "profitMargins": -0.2,
            "revenueGrowth": -0.15,
            "debtToEquity": 400,
        },
        min_score=45,
    )
    assert strong.passed and strong.score > weak.score
    assert not weak.passed or weak.score < 50


def test_earnings_proximity_penalizes():
    from datetime import date, timedelta

    soon = (date.today() + timedelta(days=1)).isoformat()
    snap = score_fundamentals_from_info(
        "EARN",
        {
            "marketCap": 50e9,
            "profitMargins": 0.1,
            "revenueGrowth": 0.1,
            "earningsDate": soon,
        },
        min_score=45,
        block_earnings_within_days=2,
        today=date.today(),
    )
    assert any("Earnings" in r for r in snap.reasons)


def test_combine_quality_score_bounds():
    q = combine_quality_score(
        technical_score=80, confidence=70, fundamental_score=60, grade_score=75
    )
    assert 0 <= q <= 100


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


def test_export_filters_incomplete_checklist(tmp_path: Path):
    good = TradeOpportunity(
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
        fundamental_score=70,
        combined_quality_score=75,
        auto_trade_eligible=True,
        playbook_setup_id="trend_pullback_long",
    )
    bad = TradeOpportunity(
        rank=2,
        symbol="BAD",
        strategy="Long Call",
        entry_price=50,
        strike_prices=[55],
        expiration="2026-08-01",
        profit_target=60,
        stop_loss=45,
        maximum_risk=100,
        maximum_reward=200,
        probability_of_success=0.5,
        confidence_score=60,
        supporting_reasons=[],
        technical=_tech(),
        options=_opts(),
        direction="Bullish",
        setup_grade="A",
        checklist_passed=False,
        edge_complete=True,
        fundamental_score=70,
        combined_quality_score=75,
    )
    plan = DailyTradingPlan(
        date="2026-07-14",
        overall_market_bias="Bullish",
        market_environment_score=60,
        top_watchlist=["NVDA", "BAD"],
        ranked_opportunities=[good, bad],
        rejection_reasons=[],
        research_summary={},
        stay_in_cash=False,
    )
    book = build_auto_trade_book(plan, min_grade="B", min_fundamental_score=45, min_quality_score=55)
    assert book["entry_count"] == 1
    assert book["entries"][0]["symbol"] == "NVDA"
    assert book["entries"][0]["checklist_passed"] is True

    out = export_plan_for_execution(plan, session_dir=tmp_path, sync_dir=tmp_path / "sync")
    assert (tmp_path / "auto_trade_book.json").exists()
    assert (tmp_path / "sync" / "auto_trade_book.json").exists()
    assert out["entry_count"] == 1


def test_journal_append_roundtrip(tmp_path: Path):
    path = tmp_path / "trades.json"
    append_journal_trade(
        JournalTrade(
            symbol="NVDA",
            entry=100,
            exit=110,
            profit_loss=200,
            strategy="Long Call",
            setup_id="orb",
            setup_grade="A",
            checklist_passed=True,
            exit_reason="take_profit",
        ),
        path=path,
    )
    rows = load_journal_trades(path)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "NVDA"
    assert rows[0]["setup_id"] == "orb"
