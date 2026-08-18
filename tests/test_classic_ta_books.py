"""Classic TA top-ten gates (Minervini / Weinstein / Elder / Carter / Grimes)."""

from __future__ import annotations

from trading_agent.config import RiskConfig
from trading_agent.discipline.classic_ta_books import (
    CLASSIC_TA_TOP_TEN,
    apply_classic_ta_book_gates,
    carter_setup_r_multiple,
    elder_triple_screen,
    grimes_systematic_edge,
    minervini_vcp_breakout,
    weinstein_stage_proxy,
)
from trading_agent.models import OptionsMetrics, ScreenerCandidate, TechnicalAnalysis
from trading_agent.ranking.ranker import build_opportunities


def test_classic_catalog_ten():
    assert len(CLASSIC_TA_TOP_TEN) == 10
    authors = " ".join(b["author"] for b in CLASSIC_TA_TOP_TEN)
    assert "Murphy" in authors
    assert "Minervini" in authors
    assert "Weinstein" in authors
    assert "Elder" in authors
    assert "Carter" in authors
    assert "Grimes" in authors
    assert "Shannon" in authors
    new = [b for b in CLASSIC_TA_TOP_TEN if b["status"] == "new"]
    assert len(new) == 5


def test_minervini_blocks_failed_breakout():
    r = minervini_vcp_breakout(
        {
            "direction": "Bullish",
            "trend": "uptrend",
            "ma_alignment": "bullish",
            "relative_strength": 1.2,
            "relative_volume": 2.0,
            "pa_signals": ["failed_breakout"],
        },
        min_rvol=1.5,
        min_rs=1.0,
    )
    assert r.ok is False
    assert "failed_breakout" in r.summary


def test_minervini_soft_without_rvol_rs():
    r = minervini_vcp_breakout(
        {"direction": "Bullish", "trend": "uptrend", "ma_alignment": "bullish"},
        min_rvol=1.5,
        min_rs=1.0,
    )
    assert r.ok is True


def test_weinstein_inactive_without_stage_inputs():
    r = weinstein_stage_proxy({"direction": "Bullish"})
    assert r.ok is True
    assert "inactive" in " ".join(r.reasons).lower()


def test_weinstein_blocks_weekly_down_for_long():
    r = weinstein_stage_proxy(
        {
            "direction": "Bullish",
            "timeframe_trends": {"weekly": "downtrend", "daily": "uptrend"},
            "ema_50": 90,
            "ema_200": 100,
        }
    )
    assert r.ok is False


def test_elder_blocks_htf_disagreement():
    r = elder_triple_screen(
        {
            "direction": "Bullish",
            "timeframe_trends": {"weekly": "downtrend", "daily": "uptrend"},
            "rsi": 55,
            "entry_price": 100,
            "stop_loss": 97,
            "atr": 2,
            "proposed_risk_pct": 1.0,
        }
    )
    assert r.ok is False


def test_elder_soft_without_mtf():
    r = elder_triple_screen(
        {
            "direction": "Bullish",
            "rsi": 55,
            "entry_price": 100,
            "stop_loss": 97,
            "proposed_risk_pct": 1.0,
        }
    )
    assert r.ok is True


def test_carter_requires_rr_and_setup():
    bad = carter_setup_r_multiple(
        {
            "setup_id": "",
            "checklist_passed": True,
            "entry_price": 100,
            "stop_loss": 99,
            "profit_target": 100.5,
        },
        min_rr=1.5,
    )
    assert bad.ok is False
    good = carter_setup_r_multiple(
        {
            "setup_id": "opening_range_breakout_long",
            "checklist_passed": True,
            "entry_price": 100,
            "stop_loss": 97,
            "profit_target": 110,
        },
        min_rr=1.5,
    )
    assert good.ok is True


def test_grimes_blocks_missing_plan():
    r = grimes_systematic_edge(
        {"direction": "Bullish", "ma_alignment": "bullish", "macd_signal": "bullish"}
    )
    assert r.ok is False


def test_apply_classic_clean_pass():
    ctx = {
        "direction": "Bullish",
        "trend": "uptrend",
        "ma_alignment": "bullish",
        "macd_signal": "bullish",
        "momentum": "bullish",
        "rsi": 58,
        "relative_volume": 2.0,
        "relative_strength": 1.2,
        "entry_price": 100,
        "stop_loss": 97,
        "profit_target": 110,
        "price": 100,
        "atr": 2.5,
        "ema_50": 105,
        "ema_200": 95,
        "timeframe_trends": {"daily": "uptrend", "weekly": "uptrend"},
        "setup_id": "trend_pullback_long",
        "checklist_passed": True,
        "proposed_risk_pct": 1.0,
        "pa_signals": [],
        "pattern_summary": "",
        "stop_basis": "support",
        "geometry_source": "structure_lfd",
    }
    res = apply_classic_ta_book_gates(ctx, min_rvol=1.5, min_rs=1.0, min_rr=1.5)
    assert res.ok is True, res.summary
    assert "Classic TA" in res.summary


def test_apply_classic_blocks_minervini_failed_breakout():
    ctx = {
        "direction": "Bullish",
        "trend": "uptrend",
        "ma_alignment": "bullish",
        "macd_signal": "bullish",
        "momentum": "bullish",
        "rsi": 58,
        "relative_volume": 2.0,
        "relative_strength": 1.2,
        "entry_price": 100,
        "stop_loss": 97,
        "profit_target": 110,
        "atr": 2.5,
        "ema_50": 105,
        "ema_200": 95,
        "timeframe_trends": {"daily": "uptrend", "weekly": "uptrend"},
        "setup_id": "trend_pullback_long",
        "checklist_passed": True,
        "proposed_risk_pct": 1.0,
        "pa_signals": ["failed_breakout"],
    }
    res = apply_classic_ta_book_gates(ctx)
    assert res.ok is False
    assert any("Minervini" in b for b in res.blocked_by)


def test_build_opportunities_blocks_classic_minervini_failed_breakout():
    """Minervini classic gate rejects failed_breakout after SMB/TA pass."""
    risk = RiskConfig(
        min_confidence_score=50,
        prefer_a_tier_only=False,
        min_setup_grade="C",
        top_candidates=5,
        require_playbook_checklist=False,
        require_edge_package=True,
        enforce_mtf_gate=True,
        enforce_smb_book_gates=True,
        enforce_ta_book_gates=True,
        enforce_classic_ta_book_gates=True,
        enforce_fundamental_gate=False,
        min_combined_quality_score=0.0,
        oneil_min_rvol=1.5,
        classic_min_rvol=1.5,
        classic_min_rs=0.0,
        classic_min_rr=1.5,
        ta_pring_min_rvol=1.2,
        ta_min_indicator_confluence=2,
    )
    tech = TechnicalAnalysis(
        symbol="FAIL",
        trend="uptrend",
        rsi=58,
        macd_signal="bullish",
        adx=28,
        atr=3,
        bollinger_position="mid",
        support=100,
        resistance=130,
        relative_strength=1.2,
        vwap_relation="above",
        ma_alignment="bullish",
        volume_profile_bias="accumulation",
        score=78,
        timeframe_trends={"daily": "uptrend", "weekly": "uptrend"},
        timeframe_alignment="aligned_bullish",
        breakout_state="breakout",
        momentum="bullish",
        ema_9=112,
        ema_20=110,
        ema_50=105,
        ema_200=95,
        candle_patterns=["hammer"],
        # Avoid Bulkowski hard-block tokens in blob; Minervini still sees failed_breakout
        pa_signals=["failed_breakout_quality"],
        pattern_summary="hammer(bullish) failed_breakout",
    )
    cand = ScreenerCandidate(
        symbol="FAIL",
        price=115,
        volume=8_000_000,
        avg_daily_volume=5_000_000,
        relative_volume=2.8,
        market_cap=2e12,
        sector="Technology",
        open_interest=8000,
        bid_ask_spread_pct=1.0,
        institutional_score=75,
        options_volume=20000,
        options_liquidity_score=75,
    )
    opts = OptionsMetrics(
        symbol="FAIL",
        implied_volatility=28,
        iv_rank=35,
        iv_percentile=40,
        expected_move_pct=2,
        delta=0.55,
        gamma=0.04,
        theta=-0.04,
        vega=0.12,
        unusual_activity=True,
        institutional_flow_bias="bullish",
        liquidity_score=75,
        probability_of_profit=0.58,
        bid_ask_spread_pct=1.2,
    )
    # Disable Bulkowski by using classic-only path: keep ta on but avoid strong PA tokens
    # "failed_breakout" substring is in pattern_summary for Minervini; Bulkowski also matches
    # failed_breakout — so turn off investopedia TA and keep classic on.
    risk.enforce_ta_book_gates = False
    rej = []
    opps = build_opportunities([(cand, tech, opts)], risk, rail_rejections=rej)
    assert opps == []
    assert any(
        "Minervini" in r.reason or "Classic TA" in r.reason for r in rej
    ), [r.reason for r in rej]
