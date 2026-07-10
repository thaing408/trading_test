"""Unit tests for CIO final decisions."""

from trading_agent.cio.config import CIOConfig
from trading_agent.cio.decisions import decide_candidate, process_all_candidates
from trading_agent.cio.models import PhaseContext, TradeCandidate


def _candidate(**kw):
    defaults = {
        "symbol": "NVDA",
        "direction": "Bullish",
        "strategy": "Debit Call Spread",
        "entry_price": 130.0,
        "strike_prices": [130.0, 135.0],
        "expiration": "2026-08-15",
        "profit_target": 136.0,
        "stop_loss": 126.0,
        "maximum_risk": 400.0,
        "maximum_reward": 1000.0,
        "probability_of_success": 0.58,
        "confidence_score": 72.0,
        "primary_catalyst": "earnings beat",
        "catalyst_type": "earnings",
        "technical_summary": "strong setup",
        "technical_confirmations": ["trend:uptrend", "vwap:above", "macd:bullish", "rsi:58"],
        "options_summary": "liquid",
        "open_interest": 15000,
        "daily_options_volume": 45000,
        "bid_ask_spread_pct": 1.2,
        "iv_rank": 42.0,
        "expected_move_pct": 4.5,
        "probability_of_profit": 0.58,
        "liquidity_score": 85.0,
        "sector": "Technology",
        "correlation_group": "semiconductors",
    }
    defaults.update(kw)
    return TradeCandidate(**defaults)


def _context(**kw):
    defaults = {
        "overall_market_bias": "Bullish",
        "market_environment_score": 65.0,
        "market_regime": "bullish",
    }
    defaults.update(kw)
    return PhaseContext(**defaults)


def test_approves_strong_candidate():
    decision, _, scorecard, _, trade = decide_candidate(_candidate(), _context(), CIOConfig())
    assert decision.startswith("Approve")
    assert trade is not None
    assert trade.ticker == "NVDA"
    assert trade.why_it_works
    assert trade.why_it_fails
    assert trade.thesis_invalidation
    assert trade.hedge_fund_approve
    assert trade.conviction_score > 0
    assert scorecard.hedge_fund_standard is True or decision == "Approve with Modifications"


def test_rejects_speculative_catalyst():
    decision, _, _, _, trade = decide_candidate(
        _candidate(symbol="TSLA", primary_catalyst="Twitter hype", catalyst_type="social_media"),
        _context(intraday_flags={"TSLA": "Exit"}),
        CIOConfig(),
    )
    assert decision == "Reject"
    assert trade is None


def test_phase2_exit_vetoes_approval():
    decision, explanation, _, _, trade = decide_candidate(
        _candidate(symbol="TSLA", primary_catalyst="earnings", catalyst_type="earnings"),
        _context(intraday_flags={"TSLA": "Exit"}),
        CIOConfig(),
    )
    assert decision == "Reject"
    assert "Phase 2" in explanation


def test_watchlist_for_low_confidence():
    decision, _, _, _, trade = decide_candidate(
        _candidate(
            confidence_score=52.0,
            probability_of_success=0.48,
            technical_confirmations=["trend:uptrend", "macd:bullish", "vwap:above", "rsi:50"],
        ),
        _context(),
        CIOConfig(min_confidence=60.0),
    )
    assert decision in ("Watchlist Only", "Reject", "Delay", "Approve with Modifications")
    if decision == "Watchlist Only":
        assert trade is None


def test_stay_in_cash_rejects_new_risk():
    decision, explanation, _, _, trade = decide_candidate(
        _candidate(),
        _context(stay_in_cash=True),
        CIOConfig(),
    )
    assert decision == "Reject"
    assert trade is None
    assert "cash" in explanation.lower() or "preservation" in explanation.lower()


def test_process_fixture_candidates():
    from trading_agent.cio.loader import load_from_fixture

    candidates, context = load_from_fixture(None)
    approved, modified, rejected = process_all_candidates(candidates, context, CIOConfig())
    book = approved + modified
    assert book
    assert rejected
    symbols_approved = {t.ticker for t in book}
    symbols_rejected = {r.ticker for r in rejected}
    assert "NVDA" in symbols_approved
    assert "TSLA" in symbols_rejected
    # Ranked by conviction
    if len(book) > 1:
        assert book[0].conviction_score >= book[1].conviction_score


def test_weak_environment_portfolio_cash():
    approved, modified, rejected = process_all_candidates(
        [_candidate()],
        _context(market_environment_score=30.0),
        CIOConfig(),
    )
    assert approved == []
    assert modified == []
    assert any(r.ticker == "PORTFOLIO" for r in rejected)
