"""Unit tests for Douglas / Steenbarger / Shannon / Bellafiore discipline rails."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trading_agent.discipline.edge import validate_edge_package
from trading_agent.discipline.mtf_gate import apply_mtf_gate, is_a_tier_mtf_eligible
from trading_agent.discipline.playbook import (
    PLAYBOOK_CATALOG,
    evaluate_checklist,
    get_setup,
    require_playbook_pass,
)
from trading_agent.discipline.process import (
    process_insights_from_trades,
    score_process,
    setup_attribution_stats,
)
from trading_agent.discipline.rails import (
    SessionRiskState,
    check_discipline_rails,
    symbol_in_cooldown,
)
from trading_agent.ranking.grades import assign_setup_grade
from trading_agent.models import OptionsMetrics, ScreenerCandidate, TechnicalAnalysis


def _tech(**kw):
    base = dict(
        symbol="NVDA",
        trend="uptrend",
        rsi=55.0,
        macd_signal="bullish",
        adx=25.0,
        atr=2.0,
        bollinger_position="mid",
        support=100.0,
        resistance=120.0,
        relative_strength=1.1,
        vwap_relation="above",
        ma_alignment="bullish",
        volume_profile_bias="accumulation",
        score=70.0,
        timeframe_trends={"daily": "uptrend", "weekly": "uptrend", "1h": "uptrend"},
        timeframe_alignment="aligned_bullish",
        breakout_state="breakout",
        momentum="bullish",
    )
    base.update(kw)
    return TechnicalAnalysis(**base)


def _opts(**kw):
    base = dict(
        symbol="NVDA",
        implied_volatility=30.0,
        iv_rank=40.0,
        iv_percentile=45.0,
        expected_move_pct=2.0,
        delta=0.5,
        gamma=0.05,
        theta=-0.05,
        vega=0.1,
        unusual_activity=False,
        institutional_flow_bias="bullish",
        liquidity_score=70.0,
        probability_of_profit=0.55,
    )
    base.update(kw)
    return OptionsMetrics(**base)


def _cand(**kw):
    base = dict(
        symbol="NVDA",
        price=110.0,
        volume=5_000_000,
        avg_daily_volume=4_000_000,
        relative_volume=2.5,
        market_cap=1e12,
        sector="Technology",
        open_interest=5000,
        bid_ask_spread_pct=1.0,
        institutional_score=70.0,
        options_volume=10000,
        options_liquidity_score=70.0,
        gap_pct=0.5,
    )
    base.update(kw)
    return ScreenerCandidate(**base)


# --- Bellafiore playbook ---


def test_playbook_checklist_pass_opening_range():
    setup = get_setup("opening_range_breakout_long")
    assert setup is not None
    ctx = {
        "direction": "Bullish",
        "breakout_state": "breakout",
        "timeframe_alignment": "aligned_bullish",
        "trend": "uptrend",
        "adx": 22,
        "relative_volume": 2.5,
        "entry_price": 100,
        "stop_loss": 97,
        "profit_target": 106,
    }
    result = evaluate_checklist(setup, ctx)
    assert result.passed is True
    assert result.failed_ids == []


def test_playbook_checklist_fail_missing_rvol():
    setup = get_setup("opening_range_breakout_long")
    ctx = {
        "direction": "Bullish",
        "breakout_state": "breakout",
        "timeframe_alignment": "aligned_bullish",
        "adx": 22,
        "relative_volume": 0.8,
        "entry_price": 100,
        "stop_loss": 97,
        "profit_target": 106,
    }
    result = evaluate_checklist(setup, ctx)
    assert result.passed is False
    assert "rvol_participation" in result.failed_ids


def test_require_playbook_rejects_incomplete():
    ok, sid, reason, _ = require_playbook_pass(
        direction="Bullish",
        strategy_name="Long Call",
        context={
            "direction": "Bullish",
            "timeframe_alignment": "aligned_bullish",
            "trend": "uptrend",
            "relative_volume": 0.5,
            "rsi": 50,
            "entry_price": 100,
            "stop_loss": 95,
            "profit_target": 110,
        },
        require_named=True,
    )
    assert ok is False
    assert "checklist failed" in reason.lower() or "FAIL" in reason


# --- Shannon MTF ---


def test_mtf_conflict_forces_f():
    gate = apply_mtf_gate(
        direction="Bullish",
        timeframe_alignment="conflicting",
        timeframe_trends={"daily": "uptrend", "weekly": "downtrend"},
        proposed_grade="A",
    )
    assert gate.allowed is False
    assert gate.force_grade == "F"


def test_mtf_long_against_htf_bearish_blocked():
    gate = apply_mtf_gate(
        direction="Bullish",
        timeframe_alignment="mixed",
        timeframe_trends={"weekly": "downtrend", "daily": "downtrend"},
        proposed_grade="A",
    )
    assert gate.allowed is False
    assert gate.force_grade == "F"


def test_mtf_aligned_a_tier_eligible():
    assert is_a_tier_mtf_eligible(
        direction="Bullish",
        timeframe_alignment="aligned_bullish",
        timeframe_trends={"daily": "uptrend", "weekly": "uptrend"},
    )


def test_assign_setup_grade_conflict_not_a_tier():
    tech = _tech(
        timeframe_alignment="conflicting",
        timeframe_trends={"daily": "uptrend", "weekly": "downtrend"},
        score=90.0,
    )
    result = assign_setup_grade(
        tech, _opts(), _cand(), quality=90.0, confidence=90.0, direction="Bullish"
    )
    assert result.grade == "F"
    assert not result.is_tradeable or result.grade == "F"
    assert any("Shannon" in r or "conflicting" in r.lower() for r in result.reasons)


# --- Douglas edge ---


def test_edge_complete_ok():
    v = validate_edge_package(
        direction="Bullish",
        entry_price=100,
        stop_loss=95,
        profit_target=110,
        maximum_risk=500,
        maximum_reward=1000,
        size_units=1,
    )
    assert v.ok is True
    assert v.package is not None
    assert v.package.risk_reward >= 1.0


def test_edge_missing_stop_fails_closed():
    v = validate_edge_package(
        direction="Bullish",
        entry_price=100,
        stop_loss=0,
        profit_target=110,
        maximum_risk=500,
    )
    assert v.ok is False
    assert "stop_loss" in v.missing


def test_edge_feeling_size_boost_rejected():
    v = validate_edge_package(
        direction="Bullish",
        entry_price=100,
        stop_loss=95,
        profit_target=110,
        maximum_risk=500,
        payload={"feeling_size_boost": True},
    )
    assert v.ok is False
    assert "fixed_size_only" in v.missing or any("feeling" in r.lower() for r in v.reasons)


# --- Rails / cool-down ---


def test_cooldown_blocks_revenge_reentry():
    now = datetime(2026, 7, 14, 16, 0, tzinfo=timezone.utc)
    stop_outs = [{"symbol": "TSLA", "time": (now - timedelta(minutes=10)).isoformat()}]
    cooling, msg = symbol_in_cooldown("TSLA", stop_outs, now=now, cooldown_minutes=60)
    assert cooling is True
    assert "cool-down" in msg.lower() or "revenge" in msg.lower()


def test_discipline_rails_max_concurrent_and_risk():
    state = SessionRiskState(
        open_symbols=["AAPL", "MSFT", "NVDA"],
        open_risk_pct=5.5,
        max_concurrent_plays=3,
        max_new_risk_pct=6.0,
        max_risk_per_trade_pct=2.0,
        cooldown_minutes=60,
    )
    decision = check_discipline_rails(
        symbol="AMD",
        proposed_risk_pct=1.5,
        state=state,
    )
    assert decision.allowed is False
    assert any("concurrent" in r.lower() for r in decision.reasons)


def test_discipline_rails_stop_cooldown():
    now = datetime(2026, 7, 14, 15, 0, tzinfo=timezone.utc)
    state = SessionRiskState(
        open_symbols=[],
        open_risk_pct=0.0,
        stop_outs=[{"symbol": "QQQ", "time": (now - timedelta(minutes=5)).isoformat()}],
        cooldown_minutes=60,
        max_concurrent_plays=3,
        max_new_risk_pct=6.0,
        max_risk_per_trade_pct=2.0,
    )
    decision = check_discipline_rails(
        symbol="QQQ",
        proposed_risk_pct=1.0,
        state=state,
        now=now,
    )
    assert decision.allowed is False
    assert any("cool-down" in r.lower() or "revenge" in r.lower() for r in decision.reasons)


# --- Process review ---


def test_process_score_and_attribution_insights():
    trades = [
        {
            "setup_id": "opening_range_breakout_long",
            "setup_name": "Opening Range Breakout Long",
            "checklist_passed": True,
            "plan_adherence": 90,
            "grade_at_entry": "A",
            "profit_loss": 200,
            "followed_stop": True,
            "revenge_reentry": False,
        },
        {
            "setup_id": "mean_reversion_long",
            "setup_name": "Mean Reversion Long",
            "checklist_passed": False,
            "plan_adherence": 30,
            "grade_at_entry": "C",
            "profit_loss": 50,
            "followed_stop": False,
            "revenge_reentry": True,
        },
    ]
    stats = setup_attribution_stats(trades)
    assert "opening_range_breakout_long" in stats
    assert stats["opening_range_breakout_long"]["avg_process_score"] > stats[
        "mean_reversion_long"
    ]["avg_process_score"]

    insights = process_insights_from_trades(trades)
    assert insights
    assert any("process" in i.lower() or "play" in i.lower() for i in insights)
    assert any("revenge" in i.lower() or "cool-down" in i.lower() for i in insights)

    ps = score_process(
        setup_id="opening_range_breakout_long",
        checklist_passed=True,
        plan_adherence=90,
        grade_at_entry="A",
    )
    assert ps.process_score >= 60


def test_catalog_has_seed_plays():
    assert len(PLAYBOOK_CATALOG) >= 3
    assert "trend_pullback_long" in PLAYBOOK_CATALOG
