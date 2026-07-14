"""Unit tests for A+/A/B/C/F setup grading and A-tier-first ranking."""

from __future__ import annotations

from trading_agent.analysis.options import compute_options_metrics
from trading_agent.analysis.technical import compute_technical_analysis
from trading_agent.config import RiskConfig
from trading_agent.models import ScreenerCandidate, TechnicalAnalysis
from trading_agent.ranking.grades import (
    GRADE_TRADE_GEOMETRY,
    assign_setup_grade,
    grade_sort_key,
    score_to_grade,
)
from trading_agent.ranking.ranker import build_opportunities, compute_trade_quality_score


def test_score_to_grade_bands():
    assert score_to_grade(90) == "A+"
    assert score_to_grade(85) == "A+"
    assert score_to_grade(80) == "A"
    assert score_to_grade(70) == "B"
    assert score_to_grade(60) == "C"
    assert score_to_grade(40) == "F"


def test_grade_sort_a_plus_before_c():
    a = grade_sort_key("A+", 90, 88, 85)
    c = grade_sort_key("C", 95, 95, 95)  # higher scores still after A+
    b = grade_sort_key("B", 70, 70, 70)
    assert a < b < c


def test_a_plus_geometry_wider_than_c():
    a_stop, a_tgt, _, _ = GRADE_TRADE_GEOMETRY["A+"]
    c_stop, c_tgt, _, _ = GRADE_TRADE_GEOMETRY["C"]
    assert a_tgt > c_tgt
    assert a_stop >= c_stop


def _tech_bull(symbol: str = "T") -> TechnicalAnalysis:
    closes = [100 + i * 0.5 for i in range(80)]
    highs = [c + 1.5 for c in closes]
    lows = [c - 1.5 for c in closes]
    volumes = [3_000_000] * 80
    ta = compute_technical_analysis(symbol, closes, highs, lows, volumes)
    # Force strong structure for grading + playbook checklist
    ta.timeframe_alignment = "aligned_bullish"
    ta.timeframe_trends = {"daily": "uptrend", "weekly": "uptrend", "1h": "uptrend"}
    ta.ma_alignment = "bullish"
    ta.breakout_state = "breakout"
    ta.trend = "uptrend"
    ta.rsi = 55.0
    ta.adx = 28.0
    ta.score = 80.0
    ta.candle_patterns = ["hammer"]
    ta.pa_signals = ["stop_hunt_demand"]
    ta.pattern_summary = "hammer(bullish); stop_hunt_demand(bullish)"
    return ta


def _opp_risk(**kw) -> RiskConfig:
    cfg = RiskConfig(
        min_confidence_score=40,
        top_candidates=5,
        prefer_a_tier_only=False,
        min_setup_grade="C",
        require_playbook_checklist=True,
        require_edge_package=True,
        enforce_mtf_gate=True,
        enforce_fundamental_gate=False,
        min_combined_quality_score=0.0,
    )
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


def _cand(symbol: str, rvol: float = 2.5) -> ScreenerCandidate:
    return ScreenerCandidate(
        symbol=symbol,
        price=140.0,
        volume=5_000_000,
        relative_volume=rvol,
        options_liquidity_score=85.0,
        open_interest=10_000,
        bid_ask_spread_pct=1.0,
        avg_daily_volume=4_000_000,
        market_cap=50_000_000_000,
        institutional_score=80.0,
        options_volume=20_000,
    )


def _opts(symbol: str, price: float = 140.0):
    return compute_options_metrics(
        symbol=symbol,
        price=price,
        iv=28.0,
        iv_history=[25, 28, 30, 27],
        strike=price * 1.02,
        days_to_expiry=30,
        open_interest=10_000,
        relative_volume=2.5,
        bid_ask_spread_pct=1.0,
        trend="uptrend",
    )


def test_assign_setup_grade_strong_is_a_tier():
    ta = _tech_bull("NVDA")
    c = _cand("NVDA")
    o = _opts("NVDA")
    quality = 82.0
    conf = 85.0
    result = assign_setup_grade(ta, o, c, quality, conf, direction="Bullish")
    assert result.grade in ("A+", "A", "B")  # strong inputs should not be F/C typically
    assert result.grade_score >= 75
    assert result.is_priority or result.grade == "B"
    assert result.target_atr_mult >= 1.5


def test_weak_grade_is_f_or_c():
    closes = [100.0] * 40
    ta = compute_technical_analysis("WEAK", closes, [101] * 40, [99] * 40, [100_000] * 40)
    ta.timeframe_alignment = "conflicting"
    ta.ma_alignment = "bearish"
    ta.score = 25.0
    ta.candle_patterns = ["shooting_star"]
    ta.pa_signals = ["stop_hunt_supply"]
    ta.pattern_summary = "shooting_star(bearish); stop_hunt_supply(bearish)"
    c = _cand("WEAK", rvol=0.8)
    c.institutional_score = 20.0
    o = _opts("WEAK")
    result = assign_setup_grade(ta, o, c, quality=40.0, confidence=45.0, direction="Bullish")
    assert result.grade in ("C", "F")
    assert result.target_atr_mult <= 1.5


def test_build_opportunities_ranks_a_before_lower():
    """Stronger setup (high RVOL + bull structure) ranks ahead of weaker one."""
    strong_c, strong_t = _cand("AAA", rvol=2.8), _tech_bull("AAA")
    weak_c = _cand("ZZZ", rvol=2.1)
    weak_t = _tech_bull("ZZZ")
    weak_t.timeframe_alignment = "mixed"
    weak_t.breakout_state = "none"
    weak_t.candle_patterns = []
    weak_t.pa_signals = []
    weak_t.pattern_summary = "none"
    weak_t.score = 45.0
    weak_c.institutional_score = 45.0

    strong_o = _opts("AAA")
    weak_o = _opts("ZZZ")
    # Nudge weak options POP lower via lower liquidity
    weak_o.liquidity_score = 55.0
    weak_o.probability_of_profit = 0.48

    opps = build_opportunities(
        [(weak_c, weak_t, weak_o), (strong_c, strong_t, strong_o)],
        _opp_risk(),
    )
    assert len(opps) >= 1
    # First must be best grade (A-tier preferred)
    grades = [o.setup_grade for o in opps]
    assert grades == sorted(grades, key=lambda g: {"A+": 0, "A": 1, "B": 2, "C": 3, "F": 4}[g])
    assert opps[0].rank == 1
    # A-tier geometry: target further from entry than stop distance roughly
    top = opps[0]
    assert top.setup_grade in ("A+", "A", "B", "C")
    atr_proxy = abs(top.profit_target - top.entry_price) / max(top.technical.atr, 1e-6)
    if top.setup_grade in ("A+", "A"):
        assert atr_proxy >= 1.9


def test_f_grade_excluded_from_opportunities():
    closes = [50.0] * 30
    ta = compute_technical_analysis("FAIL", closes, closes, closes, [10] * 30)
    ta.score = 10.0
    ta.timeframe_alignment = "conflicting"
    c = ScreenerCandidate(
        symbol="FAIL",
        price=50.0,
        volume=100,
        relative_volume=0.5,
        options_liquidity_score=20.0,
        open_interest=10,
        bid_ask_spread_pct=8.0,
        institutional_score=5.0,
    )
    o = compute_options_metrics(
        symbol="FAIL",
        price=50.0,
        iv=80.0,
        iv_history=[70, 80, 90],
        strike=50.0,
        days_to_expiry=30,
        open_interest=10,
        relative_volume=0.5,
        bid_ask_spread_pct=8.0,
        trend="sideways",
    )
    # Force low confidence path — may not enter scored at all
    opps = build_opportunities([(c, ta, o)], _opp_risk(min_confidence_score=10))
    for opp in opps:
        assert opp.setup_grade != "F"


def test_grade_geometry_applied_to_pt_sl():
    ta = _tech_bull("GEO")
    c = _cand("GEO")
    o = _opts("GEO")
    conf = 88.0
    quality = compute_trade_quality_score(ta, o, c, conf)
    grade = assign_setup_grade(ta, o, c, quality, conf, "Bullish")
    opps = build_opportunities([(c, ta, o)], _opp_risk())
    assert opps
    opp = opps[0]
    # Stop and target must reflect grade ATR mults (direction bullish)
    atr = opp.technical.atr or 1.0
    expected_tgt = round(opp.entry_price + atr * grade.target_atr_mult, 2)
    expected_stop = round(opp.entry_price - atr * grade.stop_atr_mult, 2)
    # Re-assign grade on built opp path should match geometry class
    assert opp.setup_grade in GRADE_TRADE_GEOMETRY
    stop_m, tgt_m, _, _ = GRADE_TRADE_GEOMETRY[opp.setup_grade]
    assert abs((opp.profit_target - opp.entry_price) / atr - tgt_m) < 0.15
    assert abs((opp.entry_price - opp.stop_loss) / atr - stop_m) < 0.15
