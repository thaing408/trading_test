"""Tests for SMB top-ten book mechanisms (https://www.smbtraining.com/blog/top-ten-trading-books)."""

from __future__ import annotations

from trading_agent.config import RiskConfig
from trading_agent.discipline.smb_books import (
    SMB_TOP_TEN,
    apply_smb_book_gates,
    dalton_value_area,
    kiev_commitment,
    livermore_tape_and_cut,
    oneil_can_slim_proxy,
    smb_process_habit_lines,
    system2_and_observer,
    wizards_risk_cap,
)
from trading_agent.models import OptionsMetrics, ScreenerCandidate, TechnicalAnalysis
from trading_agent.ranking.ranker import build_opportunities


def test_smb_catalog_has_ten_entries():
    assert len(SMB_TOP_TEN) == 10
    titles = " ".join(b["title"] for b in SMB_TOP_TEN)
    assert "PlayBook" in titles or "Playbook" in titles
    assert "Reminiscences" in titles
    assert "Kahneman" in " ".join(b["author"] for b in SMB_TOP_TEN) or "Fast and Slow" in titles


def test_livermore_blocks_long_against_downtrend():
    r = livermore_tape_and_cut(
        {"direction": "Bullish", "trend": "downtrend", "stop_loss": 95, "entry_price": 100}
    )
    assert r.ok is False
    assert any("tape" in x.lower() or "trend" in x.lower() for x in r.reasons)


def test_livermore_blocks_average_loser():
    r = livermore_tape_and_cut(
        {
            "direction": "Bullish",
            "trend": "uptrend",
            "stop_loss": 95,
            "averaging_down_loser": True,
        }
    )
    assert r.ok is False
    assert any("average" in x.lower() for x in r.reasons)


def test_wizards_risk_cap():
    ok = wizards_risk_cap({"proposed_risk_pct": 1.5}, max_risk_per_trade_pct=2.0)
    assert ok.ok is True
    bad = wizards_risk_cap({"proposed_risk_pct": 5.0}, max_risk_per_trade_pct=2.0)
    assert bad.ok is False


def test_oneil_rvol_floor():
    bad = oneil_can_slim_proxy(
        {"relative_volume": 0.8, "breakout_state": "breakout", "direction": "Bullish"},
        min_rvol=1.5,
    )
    assert bad.ok is False
    good = oneil_can_slim_proxy(
        {
            "relative_volume": 2.5,
            "breakout_state": "breakout",
            "direction": "Bullish",
            "setup_id": "trend_pullback_long",
        },
        min_rvol=1.5,
    )
    assert good.ok is True


def test_dalton_mean_reversion_inside_value_blocked():
    r = dalton_value_area(
        {
            "session_high": 110,
            "session_low": 100,
            "price": 105,  # mid value
            "setup_id": "mean_reversion_long",
            "direction": "Bullish",
        }
    )
    assert r.ok is False
    assert any("value" in x.lower() for x in r.reasons)


def test_kiev_daily_loss_halt():
    r = kiev_commitment({"daily_loss_halt": True, "checklist_passed": True})
    assert r.ok is False


def test_system2_revenge_and_fomo():
    r = system2_and_observer({"revenge_reentry": True})
    assert r.ok is False
    fomo = system2_and_observer(
        {
            "setup_id": "opening_range_breakout_long",
            "breakout_state": "breakout",
            "relative_volume": 0.5,
        }
    )
    assert fomo.ok is False


def test_apply_smb_gates_pass_clean_context():
    ctx = {
        "direction": "Bullish",
        "trend": "uptrend",
        "breakout_state": "breakout",
        "relative_volume": 2.5,
        "relative_strength": 1.2,
        "entry_price": 100,
        "stop_loss": 97,
        "profit_target": 108,
        "price": 100,
        "support": 95,
        "resistance": 110,
        "setup_id": "trend_pullback_long",
        "checklist_passed": True,
        "proposed_risk_pct": 1.5,
        "base_risk_pct": 2.0,
    }
    res = apply_smb_book_gates(ctx, max_risk_per_trade_pct=2.0, min_rvol=1.5)
    assert res.ok is True


def test_build_opportunities_blocks_oneil_low_rvol():
    """Shipped ranker path: O'Neil RVOL floor rejects weak participation."""
    risk = RiskConfig(
        min_confidence_score=50,
        prefer_a_tier_only=False,
        min_setup_grade="C",
        top_candidates=5,
        enforce_smb_book_gates=True,
        enforce_discipline_rails=True,
        require_playbook_checklist=False,  # isolate O'Neil vs playbook RVOL
        require_edge_package=True,
        enforce_mtf_gate=True,
        enforce_fundamental_gate=False,
        min_combined_quality_score=0.0,
        oneil_min_rvol=1.5,
    )
    tech2 = TechnicalAnalysis(
        symbol="WEAK",
        trend="uptrend",
        rsi=52,
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
    )
    weak_vol = ScreenerCandidate(
        symbol="WEAK",
        price=115,
        volume=1_000_000,
        relative_volume=0.5,  # O'Neil fail
        options_liquidity_score=75,
        open_interest=8000,
        bid_ask_spread_pct=1.0,
        avg_daily_volume=5_000_000,
        market_cap=2e12,
        institutional_score=75,
        options_volume=20000,
    )
    opts2 = OptionsMetrics(
        symbol="WEAK",
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
    rej = []
    opps = build_opportunities(
        [(weak_vol, tech2, opts2)],
        risk,
        rail_rejections=rej,
    )
    assert opps == []
    assert any("O'Neil" in r.reason or "RVOL" in r.reason for r in rej), [r.reason for r in rej]


def test_smb_habit_lines_nonempty():
    lines = smb_process_habit_lines()
    assert len(lines) >= 2
    assert any("deliberate" in x.lower() or "observer" in x.lower() for x in lines)
