"""CIO visibility over research board + OHLCV source (IBKR research-only)."""

from __future__ import annotations

from trading_agent.cio.loader import build_cio_approval_inputs, _research_board_from_candidates
from trading_agent.cio.models import TradeCandidate
from trading_agent.cio.pipeline import run_cio_pipeline
from trading_agent.cio.config import CIOConfig
from trading_agent.models import (
    DailyTradingPlan,
    OptionsMetrics,
    TechnicalAnalysis,
    TradeOpportunity,
)
from trading_agent.session.play_formatter import format_cio_plays


def _tech() -> TechnicalAnalysis:
    return TechnicalAnalysis(
        symbol="QQQ",
        trend="uptrend",
        rsi=55.0,
        macd_signal="bullish",
        adx=25.0,
        atr=2.0,
        bollinger_position="mid",
        support=100.0,
        resistance=110.0,
        relative_strength=1.0,
        vwap_relation="above",
        ma_alignment="bullish",
        volume_profile_bias="neutral",
        score=70.0,
        timeframe_alignment="aligned",
        breakout_state="none",
        momentum="bullish",
    )


def _opts() -> OptionsMetrics:
    return OptionsMetrics(
        symbol="QQQ",
        implied_volatility=30.0,
        iv_rank=40.0,
        iv_percentile=45.0,
        expected_move_pct=3.0,
        delta=0.5,
        gamma=0.01,
        theta=-0.05,
        vega=0.1,
        unusual_activity=False,
        institutional_flow_bias="neutral",
        liquidity_score=70.0,
        probability_of_profit=0.55,
        open_interest=5000,
        options_volume=8000,
        bid_ask_spread_pct=2.0,
    )


def test_research_board_tags_ibkr():
    c = TradeCandidate(
        symbol="SPY",
        direction="Bullish",
        strategy="Debit Call Spread",
        entry_price=1.0,
        strike_prices=[500, 505],
        expiration="2026-08-15",
        profit_target=2.0,
        stop_loss=0.5,
        maximum_risk=100,
        maximum_reward=200,
        probability_of_success=0.55,
        confidence_score=72,
        primary_catalyst="test",
        catalyst_type="technical",
        technical_summary="ok",
        technical_confirmations=["ohlcv:ibkr"],
        options_summary="ok",
        open_interest=5000,
        daily_options_volume=10000,
        bid_ask_spread_pct=2.0,
        iv_rank=35.0,
        expected_move_pct=3.0,
        probability_of_profit=0.55,
        liquidity_score=70.0,
        sector="Broad Market",
        phase1_rank=1,
        setup_grade="A",
        market_data_source="ibkr",
    )
    sources, lines = _research_board_from_candidates([c])
    assert sources["SPY"] == "ibkr"
    assert "IBKR" in lines[0]
    assert "SPY" in lines[0]


def test_build_cio_inputs_carries_market_data_source():
    opp = TradeOpportunity(
        rank=1,
        symbol="QQQ",
        strategy="Long Call",
        entry_price=5.0,
        strike_prices=[450.0],
        expiration="2026-08-15",
        profit_target=8.0,
        stop_loss=2.5,
        maximum_risk=250,
        maximum_reward=500,
        probability_of_success=0.5,
        confidence_score=70,
        supporting_reasons=["IBKR research bars"],
        technical=_tech(),
        options=_opts(),
        direction="Bullish",
        setup_grade="A",
        market_data_source="ibkr",
    )
    plan = DailyTradingPlan(
        date="2026-08-02",
        overall_market_bias="Bullish",
        market_environment_score=65.0,
        top_watchlist=["QQQ"],
        ranked_opportunities=[opp],
        rejection_reasons=[],
        research_summary={
            "ohlcv_sources": {"QQQ": "ibkr"},
            "ohlcv_research_note": "Bars research-only",
        },
        stay_in_cash=False,
    )
    candidates, context = build_cio_approval_inputs(plan, fixture_mode=False)
    assert len(candidates) == 1
    assert candidates[0].market_data_source == "ibkr"
    assert "ohlcv:ibkr" in candidates[0].technical_confirmations
    assert context.research_data_sources.get("QQQ") == "ibkr"
    assert context.research_board_lines
    assert "IBKR" in context.research_board_lines[0]


def test_cio_discord_shows_research_board():
    config = CIOConfig(fixture_mode=True, portfolio_value=100_000)
    report = run_cio_pipeline(config)
    # Fixture candidates get market_data_source=fixture + board lines
    assert report.context.research_board_lines or report.context.research_data_sources
    text = format_cio_plays(report, title="CIO Final Approval")
    assert "Research board" in text
    assert "not IBKR execution" in text
