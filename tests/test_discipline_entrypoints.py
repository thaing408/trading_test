"""Entry-point tests: build_opportunities + performance insights (shipped paths)."""

from __future__ import annotations

from trading_agent.config import RiskConfig
from trading_agent.models import OptionsMetrics, ScreenerCandidate, TechnicalAnalysis
from trading_agent.performance.insights import generate_insights
from trading_agent.performance.models import (
    CompletedTrade,
    ConfidenceRefinement,
    DailyMetrics,
    PatternInsights,
)
from trading_agent.ranking.ranker import build_opportunities


def _tech(symbol="NVDA", **kw):
    base = dict(
        symbol=symbol,
        trend="uptrend",
        rsi=52.0,
        macd_signal="bullish",
        adx=28.0,
        atr=3.0,
        bollinger_position="mid",
        support=100.0,
        resistance=130.0,
        relative_strength=1.2,
        vwap_relation="above",
        ma_alignment="bullish",
        volume_profile_bias="accumulation",
        score=78.0,
        timeframe_trends={"daily": "uptrend", "weekly": "uptrend", "1h": "uptrend"},
        timeframe_alignment="aligned_bullish",
        breakout_state="breakout",
        momentum="bullish",
        ema_9=112.0,
        ema_20=110.0,
        ema_50=105.0,
        ema_200=95.0,
    )
    base.update(kw)
    return TechnicalAnalysis(**base)


def _opts(symbol="NVDA", **kw):
    base = dict(
        symbol=symbol,
        implied_volatility=28.0,
        iv_rank=35.0,
        iv_percentile=40.0,
        expected_move_pct=2.0,
        delta=0.55,
        gamma=0.04,
        theta=-0.04,
        vega=0.12,
        unusual_activity=True,
        institutional_flow_bias="bullish",
        liquidity_score=75.0,
        probability_of_profit=0.58,
        probability_of_touch=0.4,
        options_volume=20000,
        open_interest=8000,
        bid_ask_spread_pct=1.2,
    )
    base.update(kw)
    return OptionsMetrics(**base)


def _cand(symbol="NVDA", **kw):
    base = dict(
        symbol=symbol,
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
        gap_pct=1.0,
    )
    base.update(kw)
    return ScreenerCandidate(**base)


def test_aligned_complete_edge_play_is_tradeable():
    risk = RiskConfig(
        min_confidence_score=50.0,
        prefer_a_tier_only=False,
        min_setup_grade="C",
        top_candidates=5,
        require_playbook_checklist=True,
        require_edge_package=True,
        enforce_mtf_gate=True,
    )
    qualified = [(_cand(), _tech(), _opts())]
    opps = build_opportunities(qualified, risk)
    assert len(opps) >= 1
    opp = opps[0]
    assert opp.setup_grade in ("A+", "A", "B", "C")
    assert opp.checklist_passed is True
    assert opp.edge_complete is True
    assert opp.playbook_setup_id
    assert opp.stop_loss > 0 and opp.profit_target > 0
    assert opp.maximum_risk > 0


def test_conflicting_mtf_not_actionable():
    risk = RiskConfig(
        min_confidence_score=50.0,
        prefer_a_tier_only=False,
        min_setup_grade="C",
        top_candidates=5,
        require_playbook_checklist=True,
        require_edge_package=True,
        enforce_mtf_gate=True,
    )
    tech = _tech(
        timeframe_alignment="conflicting",
        timeframe_trends={"daily": "uptrend", "weekly": "downtrend"},
        score=90.0,
    )
    opps = build_opportunities([(_cand(), tech, _opts())], risk)
    assert opps == []


def test_missing_edge_fields_fail_closed_via_validate():
    from trading_agent.discipline.edge import validate_edge_package

    bad = validate_edge_package(
        direction="Bullish",
        entry_price=100,
        stop_loss=0,
        profit_target=0,
        maximum_risk=0,
    )
    assert bad.ok is False


def test_performance_insights_include_setup_process():
    trades = [
        CompletedTrade(
            symbol="NVDA",
            entry=100,
            exit=110,
            profit_loss=200,
            holding_time_minutes=30,
            strategy="Long Call",
            technical_setup="ORB",
            news_catalyst="",
            market_conditions="bullish",
            volatility_environment="normal",
            risk_reward_ratio=2.0,
            probability_of_success=0.55,
            confidence_score=70,
            position_size=1,
            max_drawdown=20,
            max_favorable_excursion=15,
            max_adverse_excursion=5,
            setup_id="opening_range_breakout_long",
            setup_name="Opening Range Breakout Long",
            checklist_passed=True,
            plan_adherence=85.0,
            grade_at_entry="A",
            followed_stop=True,
            revenge_reentry=False,
        ),
        CompletedTrade(
            symbol="TSLA",
            entry=200,
            exit=190,
            profit_loss=-100,
            holding_time_minutes=15,
            strategy="Long Call",
            technical_setup="chase",
            news_catalyst="",
            market_conditions="choppy",
            volatility_environment="high",
            risk_reward_ratio=1.0,
            probability_of_success=0.4,
            confidence_score=50,
            position_size=1,
            max_drawdown=50,
            max_favorable_excursion=5,
            max_adverse_excursion=40,
            setup_id="mean_reversion_long",
            setup_name="Mean Reversion Long",
            checklist_passed=False,
            plan_adherence=25.0,
            grade_at_entry="C",
            followed_stop=False,
            revenge_reentry=True,
        ),
    ]
    metrics = DailyMetrics(
        total_profit_loss=100,
        win_rate=0.5,
        average_winner=200,
        average_loser=100,
        profit_factor=2.0,
        expectancy=50,
        largest_winner=200,
        largest_loser=-100,
        trade_count=2,
        winner_count=1,
        loser_count=1,
    )
    patterns = PatternInsights(
        best_strategies=["Long Call"],
        weakest_strategies=[],
        losing_trade_causes=[],
        profitable_conditions=["bullish"],
        time_of_day_performance={},
        top_indicator_combos=[],
        top_news_catalysts=[],
    )
    refinement = ConfidenceRefinement({}, {}, {}, [])
    lessons, mistakes, improvements, habits, tomorrow = generate_insights(
        trades, metrics, patterns, refinement
    )
    blob = "\n".join(lessons + mistakes + improvements + habits + tomorrow)
    assert "Opening Range" in blob or "process" in blob.lower() or "play" in blob.lower()
    assert "revenge" in blob.lower() or "cool-down" in blob.lower() or "Mean Reversion" in blob
