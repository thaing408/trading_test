"""Investopedia TA book gates — https://www.investopedia.com/articles/personal-finance/090916/top-5-books-learn-technical-analysis.asp"""

from __future__ import annotations

from trading_agent.config import RiskConfig
from trading_agent.discipline.ta_books import (
    INVESTOPEDIA_TA_BOOKS,
    apply_investopedia_ta_gates,
    bulkowski_pattern_bias,
    murphy_indicator_confluence,
    nison_candle_alignment,
    pring_trend_volume,
    schwager_plan_entry_exit,
)
from trading_agent.models import OptionsMetrics, ScreenerCandidate, TechnicalAnalysis
from trading_agent.ranking.ranker import build_opportunities


def test_investopedia_catalog_seven():
    assert len(INVESTOPEDIA_TA_BOOKS) == 7
    authors = " ".join(b["author"] for b in INVESTOPEDIA_TA_BOOKS)
    assert "Schwager" in authors
    assert "Murphy" in authors
    assert "Nison" in authors
    assert "Bulkowski" in authors
    assert "Shannon" in authors


def test_schwager_requires_stop_and_target():
    bad = schwager_plan_entry_exit({"entry_price": 100, "stop_loss": 0, "profit_target": 0})
    assert bad.ok is False
    good = schwager_plan_entry_exit(
        {"entry_price": 100, "stop_loss": 97, "profit_target": 108}
    )
    assert good.ok is True


def test_pring_blocks_long_against_downtrend():
    r = pring_trend_volume(
        {
            "direction": "Bullish",
            "trend": "downtrend",
            "ma_alignment": "bearish",
            "relative_volume": 2.0,
        }
    )
    assert r.ok is False


def test_murphy_confluence_requires_two_votes():
    weak = murphy_indicator_confluence(
        {
            "direction": "Bullish",
            "ma_alignment": "neutral",
            "macd_signal": "neutral",
            "rsi": 50,
            "momentum": "neutral",
        },
        min_aligned=2,
    )
    assert weak.ok is False
    strong = murphy_indicator_confluence(
        {
            "direction": "Bullish",
            "ma_alignment": "bullish",
            "macd_signal": "bullish",
            "rsi": 60,
            "momentum": "bullish",
        },
        min_aligned=2,
    )
    assert strong.ok is True


def test_nison_blocks_shooting_star_on_long():
    r = nison_candle_alignment(
        {
            "direction": "Bullish",
            "candle_patterns": ["shooting_star"],
            "pattern_summary": "shooting_star(bearish)",
        }
    )
    assert r.ok is False


def test_bulkowski_blocks_failed_breakout_long():
    r = bulkowski_pattern_bias(
        {
            "direction": "Bullish",
            "pa_signals": ["failed_breakout"],
            "pattern_summary": "failed_breakout",
        }
    )
    assert r.ok is False


def test_apply_ta_gates_clean_pass():
    ctx = {
        "direction": "Bullish",
        "trend": "uptrend",
        "ma_alignment": "bullish",
        "macd_signal": "bullish",
        "rsi": 58,
        "momentum": "bullish",
        "relative_volume": 2.0,
        "entry_price": 100,
        "stop_loss": 97,
        "profit_target": 110,
        "price": 100,
        "candle_patterns": ["hammer"],
        "pa_signals": ["stop_hunt_demand"],
        "pattern_summary": "hammer(bullish)",
    }
    res = apply_investopedia_ta_gates(ctx, min_rvol=1.2, min_confluence=2)
    assert res.ok is True


def test_build_opportunities_blocks_nison_opposing_candle():
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
        oneil_min_rvol=1.5,
        ta_pring_min_rvol=1.2,
        ta_min_indicator_confluence=2,
    )
    tech = TechnicalAnalysis(
        symbol="STAR",
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
        candle_patterns=["shooting_star"],
        pa_signals=[],
        pattern_summary="shooting_star(bearish)",
    )
    cand = ScreenerCandidate(
        symbol="STAR",
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
        symbol="STAR",
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
    opps = build_opportunities([(cand, tech, opts)], risk, rail_rejections=rej)
    assert opps == []
    assert any("Nison" in r.reason or "Investopedia TA" in r.reason for r in rej), [
        r.reason for r in rej
    ]
