"""Unit tests for confidence ranking."""

from trading_agent.analysis.options import compute_options_metrics
from trading_agent.analysis.technical import compute_technical_analysis
from trading_agent.config import RiskConfig
from trading_agent.models import ScreenerCandidate
from trading_agent.ranking.ranker import build_opportunities, compute_confidence_score


def _bundle(symbol, rel_vol=1.8, oi=10000):
    closes = [100 + i for i in range(60)]
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    volumes = [2_000_000] * 60
    technical = compute_technical_analysis(symbol, closes, highs, lows, volumes)
    candidate = ScreenerCandidate(
        symbol=symbol,
        price=closes[-1],
        volume=5_000_000,
        relative_volume=rel_vol,
        options_liquidity_score=80.0,
        open_interest=oi,
        bid_ask_spread_pct=1.0,
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


def test_build_opportunities_ranks_top_five():
    bundles = [_bundle(f"SYM{i}", rel_vol=1.5 + i * 0.1) for i in range(8)]
    opps = build_opportunities(bundles, RiskConfig(min_confidence_score=50))
    assert len(opps) <= 5
    assert opps[0].rank == 1
    if len(opps) > 1:
        assert opps[0].confidence_score >= opps[1].confidence_score


def test_opportunity_has_required_trade_fields():
    c, t, o = _bundle("TRADE")
    opps = build_opportunities([(c, t, o)], RiskConfig(min_confidence_score=40))
    assert len(opps) == 1
    opp = opps[0]
    assert opp.strategy
    assert opp.entry_price > 0
    assert opp.strike_prices
    assert opp.expiration
    assert opp.maximum_risk > 0
    assert opp.maximum_reward > 0
    assert opp.supporting_reasons