"""Unit tests for confidence ranking."""

from trading_agent.analysis.options import compute_options_metrics
from trading_agent.analysis.technical import compute_technical_analysis
from trading_agent.config import RiskConfig
from trading_agent.models import ScreenerCandidate
from trading_agent.ranking.ranker import build_opportunities, compute_confidence_score


def _bundle(symbol, rel_vol=1.8, oi=10000):
    # Trending but not a pure straight line (RSI not pinned at 100 for playbook)
    closes = []
    px = 100.0
    for i in range(60):
        px += 0.8 if i % 5 else -0.3
        closes.append(px)
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    volumes = [2_000_000] * 60
    technical = compute_technical_analysis(symbol, closes, highs, lows, volumes)
    # Keep ranking fixtures free of opposing PA that TA book gates hard-block
    technical.candle_patterns = [p for p in (technical.candle_patterns or []) if "shooting" not in p]
    technical.pa_signals = [
        p
        for p in (technical.pa_signals or [])
        if "failed_breakout" not in p and "double_top" not in p
    ]
    if technical.pattern_summary and "failed_breakout" in technical.pattern_summary:
        technical.pattern_summary = "none"
    candidate = ScreenerCandidate(
        symbol=symbol,
        price=closes[-1],
        volume=5_000_000,
        relative_volume=max(rel_vol, 2.1),
        options_liquidity_score=80.0,
        open_interest=oi,
        bid_ask_spread_pct=1.0,
        avg_daily_volume=4_000_000,
        market_cap=50_000_000_000,
        institutional_score=70.0,
        options_volume=20_000,
    )
    options = compute_options_metrics(
        symbol=symbol,
        price=closes[-1],
        iv=30.0,
        iv_history=[25, 28, 30, 32, 27],
        strike=closes[-1] * 1.02,
        days_to_expiry=30,
        open_interest=oi,
        relative_volume=rel_vol,
        bid_ask_spread_pct=1.0,
        trend=technical.trend,
    )
    return candidate, technical, options


def test_confidence_score_in_range():
    c, t, o = _bundle("AAA")
    score = compute_confidence_score(t, o, c)
    assert 0 <= score <= 100


def _rank_risk(**kw) -> RiskConfig:
    """Risk config for ranking tests: allow book path without A-only starvation."""
    cfg = RiskConfig(
        min_confidence_score=40,
        prefer_a_tier_only=False,
        min_setup_grade="C",
        top_candidates=5,
        require_playbook_checklist=True,
        require_edge_package=True,
        enforce_mtf_gate=True,
        enforce_fundamental_gate=False,
        min_combined_quality_score=0.0,
    )
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


def test_build_opportunities_ranks_top_five():
    bundles = [_bundle(f"SYM{i}", rel_vol=1.5 + i * 0.1) for i in range(8)]
    opps = build_opportunities(bundles, _rank_risk(min_confidence_score=50))
    assert len(opps) <= 5
    assert len(opps) >= 1
    assert opps[0].rank == 1
    if len(opps) > 1:
        assert opps[0].confidence_score >= opps[1].confidence_score


def test_opportunity_has_required_trade_fields():
    c, t, o = _bundle("TRADE")
    opps = build_opportunities([(c, t, o)], _rank_risk())
    assert len(opps) == 1
    opp = opps[0]
    assert opp.strategy
    assert opp.entry_price > 0
    assert opp.strike_prices
    assert opp.expiration
    assert opp.maximum_risk > 0
    assert opp.maximum_reward > 0
    assert opp.supporting_reasons
    assert opp.direction
    assert opp.trade_thesis
    assert 0 <= opp.trade_quality_score <= 100
    assert opp.risks