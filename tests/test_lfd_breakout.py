"""Brandt LFD + TechCharts Type 1–4 structure risk package tests."""

from __future__ import annotations

from trading_agent.analysis.lfd_breakout import (
    BreakoutType,
    RiskPolicy,
    build_structure_risk_package,
    classify_breakout_path,
    identify_last_full_day,
    resolve_structure_from_ohlcv,
    resolve_structure_from_technical,
    structure_package_for_setup,
    trail_stop_from_structure,
)
from trading_agent.export.auto_trade_book import build_auto_trade_book
from trading_agent.methods.web_methods import BASELINE_METHODS, evaluate_methods_for_setup
from trading_agent.models import (
    DailyTradingPlan,
    OptionsMetrics,
    TechnicalAnalysis,
    TradeOpportunity,
)
from trading_agent.ranking.ranker import _trade_params
from trading_agent.strategy.selector import StrategySelection


def _ohlcv_breakout_long():
    # Range 95–100 then breakout close 102
    opens = [96, 97, 97.5, 98, 99, 100.5]
    highs = [98, 99, 99.5, 99.8, 100.0, 103]
    lows = [95, 96, 96.5, 97, 97.5, 100.2]
    closes = [97, 98, 98.5, 99, 99.5, 102]
    return opens, highs, lows, closes


def test_identify_last_full_day_long():
    opens, highs, lows, closes = _ohlcv_breakout_long()
    breakout = 100.0
    lfd = identify_last_full_day(
        highs, lows, closes, breakout_level=breakout, direction="bullish", opens=opens
    )
    assert lfd is not None
    # Last fully inside bar: high <= 100 before breakout
    assert lfd.high <= 100.0 + 1e-6
    assert lfd.low == 97.5


def test_structure_from_ohlcv_measured_move():
    opens, highs, lows, closes = _ohlcv_breakout_long()
    s = resolve_structure_from_ohlcv(highs, lows, closes, direction="bullish", opens=opens)
    assert s is not None
    assert s.source == "ohlcv_lfd"
    assert s.breakout_level >= 99.0
    assert s.measured_target > s.breakout_level
    assert s.lfd_level > 0
    assert s.negation_level <= s.lfd_level + 1e-6 or s.negation_level <= s.breakout_level


def test_structure_risk_package_prefers_lfd_not_pct():
    s = resolve_structure_from_technical(
        price=100.0,
        direction="bullish",
        support=94.0,
        resistance=99.0,
        atr=1.5,
        breakout_state="breakout",
    )
    pkg = build_structure_risk_package(
        entry_price=100.0,
        direction="bullish",
        structure=s,
        atr=1.5,
        risk_policy=RiskPolicy.LFD_TIGHT,
        stop_atr_mult=1.0,
        target_atr_mult=2.0,
        size_multiplier=1.0,
    )
    assert pkg.stop_basis == "lfd"
    assert pkg.stop_loss < 100.0
    # Stop near structure LFD, not a flat 2% hardcode (would be 98)
    assert pkg.profit_target > 100.0
    assert pkg.target_basis in ("measured_move", "atr")
    assert pkg.risk_reward >= 1.0


def test_classify_type1_type2_type3_type4():
    # Type 1 momentum
    p1 = classify_breakout_path(
        direction="bullish",
        entry_price=100,
        breakout_level=99,
        lfd_level=97,
        negation_level=94,
        current_price=103,
        session_high=103.5,
        session_low=100.5,
    )
    assert p1.breakout_type == BreakoutType.TYPE_1_MOMENTUM

    # Type 2 retest
    p2 = classify_breakout_path(
        direction="bullish",
        entry_price=100,
        breakout_level=99,
        lfd_level=97,
        negation_level=94,
        current_price=100.2,
        session_high=101,
        session_low=99.0,
    )
    assert p2.breakout_type == BreakoutType.TYPE_2_STANDARD_RETEST
    assert p2.lfd_intact is True

    # Type 3 deep
    p3 = classify_breakout_path(
        direction="bullish",
        entry_price=100,
        breakout_level=99,
        lfd_level=97,
        negation_level=94,
        current_price=96.5,
        session_high=101,
        session_low=96.0,
    )
    assert p3.breakout_type == BreakoutType.TYPE_3_DEEP_RETEST
    assert p3.negation_intact is True

    # Type 4 fail
    p4 = classify_breakout_path(
        direction="bullish",
        entry_price=100,
        breakout_level=99,
        lfd_level=97,
        negation_level=94,
        current_price=93,
        session_high=101,
        session_low=92.5,
    )
    assert p4.breakout_type == BreakoutType.TYPE_4_FAILED


def test_trail_stop_only_tightens():
    new_stop, reason = trail_stop_from_structure(
        direction="bullish",
        entry_price=100,
        current_stop=96,
        current_price=105,
        breakout_level=99,
        lfd_level=97,
        negation_level=94,
        atr=1.0,
    )
    assert new_stop >= 96
    assert new_stop < 105


def test_trade_params_sets_structure_fields():
    tech = TechnicalAnalysis(
        symbol="TEST",
        trend="uptrend",
        rsi=58,
        macd_signal="bullish",
        adx=28,
        atr=2.0,
        bollinger_position="upper",
        support=94.0,
        resistance=99.0,
        relative_strength=5.0,
        vwap_relation="above",
        ma_alignment="bullish",
        volume_profile_bias="accumulation",
        score=70,
        breakout_state="breakout",
        momentum="bullish",
    )
    opt = OptionsMetrics(
        symbol="TEST",
        implied_volatility=30,
        iv_rank=40,
        iv_percentile=40,
        expected_move_pct=4,
        delta=0.4,
        gamma=0.01,
        theta=-0.05,
        vega=0.1,
        unusual_activity=False,
        institutional_flow_bias="neutral",
        liquidity_score=70,
        probability_of_profit=0.55,
    )
    strat = StrategySelection(
        name="Long Call",
        strike_prices=[100],
        expiration_days=30,
        bias="bullish",
        direction="Bullish",
    )
    params = _trade_params(100.0, strat, opt, tech, stop_atr_mult=1.0, target_atr_mult=2.0)
    assert params["stop_loss"] < params["entry_price"] < params["profit_target"]
    assert params["stop_basis"]
    assert params["lfd_level"] > 0 or params["breakout_level"] > 0
    assert params["geometry_source"]


def test_method_lfd_structure_in_baseline():
    ids = {m.method_id for m in BASELINE_METHODS}
    assert "lfd_structure_stop" in ids
    ev = evaluate_methods_for_setup(
        BASELINE_METHODS,
        {
            "entry_price": 100,
            "stop_loss": 96,
            "profit_target": 110,
            "checklist_passed": True,
            "require_checklist": True,
            "edge_complete": True,
            "timeframe_alignment": "aligned_bullish",
            "relative_volume": 2.0,
            "proposed_risk_pct": 1.0,
            "max_risk_per_trade_pct": 2.0,
            "stop_basis": "lfd",
            "lfd_level": 96.5,
            "breakout_level": 99,
        },
    )
    assert "lfd_structure_stop" in ev["method_ids_ok"]
    assert ev["critical_fail"] is False


def test_auto_trade_book_includes_structure_fields():
    tech = TechnicalAnalysis(
        symbol="AAA",
        trend="uptrend",
        rsi=55,
        macd_signal="bullish",
        adx=25,
        atr=1.5,
        bollinger_position="middle",
        support=90,
        resistance=98,
        relative_strength=2,
        vwap_relation="above",
        ma_alignment="bullish",
        volume_profile_bias="accumulation",
        score=72,
        breakout_state="breakout",
    )
    opt = OptionsMetrics(
        symbol="AAA",
        implied_volatility=25,
        iv_rank=45,
        iv_percentile=45,
        expected_move_pct=3,
        delta=0.35,
        gamma=0.01,
        theta=-0.04,
        vega=0.08,
        unusual_activity=False,
        institutional_flow_bias="bullish",
        liquidity_score=80,
        probability_of_profit=0.6,
    )
    opp = TradeOpportunity(
        rank=1,
        symbol="AAA",
        strategy="Bull Put Credit Spread",
        entry_price=100,
        strike_prices=[97, 92],
        expiration="2026-08-15",
        profit_target=108,
        stop_loss=95,
        maximum_risk=150,
        maximum_reward=300,
        probability_of_success=0.6,
        confidence_score=75,
        supporting_reasons=["test"],
        technical=tech,
        options=opt,
        direction="Bullish",
        setup_grade="A",
        grade_score=80,
        checklist_passed=True,
        edge_complete=True,
        auto_trade_eligible=True,
        fundamental_score=60,
        combined_quality_score=70,
        defined_risk=True,
        stop_basis="lfd",
        target_basis="measured_move",
        geometry_source="hybrid",
        risk_policy="hybrid",
        lfd_level=95.5,
        breakout_level=99,
        negation_level=90,
        measured_target=108,
        pattern_height=9,
        structure_notes="test structure",
    )
    plan = DailyTradingPlan(
        date="2026-07-15",
        overall_market_bias="Bullish",
        market_environment_score=70,
        top_watchlist=["AAA"],
        ranked_opportunities=[opp],
        rejection_reasons=[],
        research_summary={},
        stay_in_cash=False,
        cash_recommendation_reason="",
    )
    book = build_auto_trade_book(plan, min_grade="B", min_fundamental_score=0, min_quality_score=0)
    assert book["entry_count"] == 1
    row = book["entries"][0]
    assert row["stop_basis"] == "lfd"
    assert row["lfd_level"] == 95.5
    assert row["breakout_level"] == 99
    assert row["measured_target"] == 108


def test_structure_package_for_setup_short():
    pkg = structure_package_for_setup(
        price=50,
        direction="bearish",
        support=48,
        resistance=53,
        atr=1.0,
        breakout_state="breakdown",
        risk_policy=RiskPolicy.HYBRID,
    )
    assert pkg.stop_loss > 50
    assert pkg.profit_target < 50
    assert pkg.structure.direction == "bearish"
