"""Options-specific method gates and ENTER package fields."""

from __future__ import annotations

from trading_agent.export.auto_trade_book import build_auto_trade_book
from trading_agent.methods.options_methods import (
    classify_strategy,
    evaluate_options_methods,
    is_defined_risk_strategy,
)
from trading_agent.models import (
    DailyTradingPlan,
    OptionsMetrics,
    TechnicalAnalysis,
    TradeOpportunity,
)
from trading_agent.session.play_formatter import format_research_plays


def test_iv_regime_blocks_credit_in_low_iv():
    r = evaluate_options_methods(
        {
            "strategy": "Bull Put Credit Spread",
            "iv_rank": 25,
            "probability_of_profit": 0.6,
            "open_interest": 2000,
            "bid_ask_spread_pct": 1.0,
            "expiration_days": 30,
            "delta": 0.3,
            "direction": "Bullish",
            "maximum_risk": 200,
            "maximum_reward": 100,
        }
    )
    assert r.critical_fail is True
    assert r.strategy_class == "credit"
    assert any("iv_regime" in f for f in r.failures)


def test_iv_regime_blocks_debit_in_high_iv():
    r = evaluate_options_methods(
        {
            "strategy": "Long Call",
            "iv_rank": 80,
            "probability_of_profit": 0.45,
            "open_interest": 5000,
            "bid_ask_spread_pct": 1.0,
            "expiration_days": 30,
            "delta": 0.55,
            "direction": "Bullish",
            "maximum_risk": 300,
            "maximum_reward": 600,
        }
    )
    assert r.critical_fail is True
    assert any("iv_regime" in f for f in r.failures)


def test_credit_ok_high_iv_defined_risk():
    r = evaluate_options_methods(
        {
            "strategy": "Bull Put Credit Spread",
            "iv_rank": 65,
            "probability_of_profit": 0.55,
            "open_interest": 3000,
            "bid_ask_spread_pct": 1.5,
            "expiration_days": 28,
            "delta": 0.25,
            "direction": "Bullish",
            "maximum_risk": 250,
            "maximum_reward": 80,
        }
    )
    assert r.critical_fail is False
    assert "iv_regime_match" in r.method_ids_ok
    assert is_defined_risk_strategy("Bull Put Credit Spread")


def test_liquidity_and_dte_gates():
    r = evaluate_options_methods(
        {
            "strategy": "Iron Condor",
            "iv_rank": 70,
            "probability_of_profit": 0.5,
            "open_interest": 50,
            "bid_ask_spread_pct": 8.0,
            "expiration_days": 2,
            "delta": 0.1,
            "direction": "Neutral",
            "maximum_risk": 200,
            "maximum_reward": 50,
        }
    )
    assert r.critical_fail is True
    assert any("liquidity" in f or "dte" in f for f in r.failures)


def test_classify_strategy():
    assert classify_strategy("Iron Condor") == "credit"
    assert classify_strategy("Long Put") == "debit"


def _tech():
    return TechnicalAnalysis(
        symbol="NVDA",
        trend="uptrend",
        rsi=55,
        macd_signal="bullish",
        adx=25,
        atr=2,
        bollinger_position="mid",
        support=100,
        resistance=120,
        relative_strength=1.1,
        vwap_relation="above",
        ma_alignment="bullish",
        volume_profile_bias="accumulation",
        score=75,
        timeframe_alignment="aligned_bullish",
    )


def _opts():
    return OptionsMetrics(
        symbol="NVDA",
        implied_volatility=40,
        iv_rank=65,
        iv_percentile=70,
        expected_move_pct=3,
        delta=0.3,
        gamma=0.05,
        theta=-0.05,
        vega=0.1,
        unusual_activity=False,
        institutional_flow_bias="bullish",
        liquidity_score=70,
        probability_of_profit=0.55,
    )


def test_export_options_enter_fields():
    opp = TradeOpportunity(
        rank=1,
        symbol="NVDA",
        strategy="Bull Put Credit Spread",
        entry_price=100,
        strike_prices=[97, 92],
        expiration="2026-08-15",
        profit_target=102,
        stop_loss=96,
        maximum_risk=250,
        maximum_reward=80,
        probability_of_success=0.55,
        confidence_score=70,
        supporting_reasons=[],
        technical=_tech(),
        options=_opts(),
        direction="Bullish",
        setup_grade="A",
        checklist_passed=True,
        edge_complete=True,
        auto_trade_eligible=True,
        fundamental_score=70,
        combined_quality_score=75,
        options_strategy_class="credit",
        iv_rank=65,
        options_pop=0.55,
        options_delta=0.3,
        expiration_days=28,
        defined_risk=True,
        method_tags=["iv_regime_match", "defined_risk"],
    )
    plan = DailyTradingPlan(
        date="2026-07-14",
        overall_market_bias="Bullish",
        market_environment_score=60,
        top_watchlist=["NVDA"],
        ranked_opportunities=[opp],
        rejection_reasons=[],
        research_summary={},
        stay_in_cash=False,
    )
    book = build_auto_trade_book(plan, min_fundamental_score=0, min_quality_score=0)
    assert book["entry_count"] == 1
    e = book["entries"][0]
    assert e["instrument"] == "options"
    assert e["options_strategy_class"] == "credit"
    assert e["iv_rank"] == 65
    assert e["pop"] == 0.55
    assert e["dte"] == 28
    assert e["defined_risk"] is True
    assert e["strike_prices"] == [97, 92]


def test_options_playbook_credit_bull_put_passes():
    from trading_agent.discipline.playbook import evaluate_checklist, get_setup

    setup = get_setup("options_credit_bull_put")
    assert setup is not None
    result = evaluate_checklist(
        setup,
        {
            "direction": "Bullish",
            "timeframe_alignment": "aligned_bullish",
            "trend": "uptrend",
            "iv_rank": 60,
            "probability_of_profit": 0.55,
            "open_interest": 2000,
            "bid_ask_spread_pct": 1.5,
            "entry_price": 100,
            "stop_loss": 95,
            "profit_target": 102,
        },
    )
    assert result.passed is True


def test_format_options_enter_cards():
    from trading_agent.session.play_formatter import format_options_enter_cards

    opp = TradeOpportunity(
        rank=1,
        symbol="NVDA",
        strategy="Bull Put Credit Spread",
        entry_price=100,
        strike_prices=[97, 92],
        expiration="2026-08-15",
        profit_target=102,
        stop_loss=96,
        maximum_risk=250,
        maximum_reward=80,
        probability_of_success=0.55,
        confidence_score=70,
        supporting_reasons=[],
        technical=_tech(),
        options=_opts(),
        direction="Bullish",
        setup_grade="A",
        playbook_setup_id="options_credit_bull_put",
        checklist_passed=True,
        edge_complete=True,
        auto_trade_eligible=True,
        defined_risk=True,
        options_strategy_class="credit",
        iv_rank=65,
        options_pop=0.55,
        options_delta=0.3,
        expiration_days=28,
    )
    plan = DailyTradingPlan(
        date="2026-07-14",
        overall_market_bias="Bullish",
        market_environment_score=60,
        top_watchlist=["NVDA"],
        ranked_opportunities=[opp],
        rejection_reasons=[],
        research_summary={},
        stay_in_cash=False,
    )
    lines = format_options_enter_cards(plan)
    assert any("AUTO-ENTER" in x for x in lines)
    assert any("ENTER NVDA" in x for x in lines)
    assert any("IVR" in x for x in lines)


def test_discord_options_fields_in_research():
    opp = TradeOpportunity(
        rank=1,
        symbol="NVDA",
        strategy="Bull Put Credit Spread",
        entry_price=100,
        strike_prices=[97, 92],
        expiration="2026-08-15",
        profit_target=102,
        stop_loss=96,
        maximum_risk=250,
        maximum_reward=80,
        probability_of_success=0.55,
        confidence_score=70,
        supporting_reasons=["t"],
        technical=_tech(),
        options=_opts(),
        direction="Bullish",
        setup_grade="A",
        playbook_setup_id="trend_pullback_long",
        checklist_passed=True,
        edge_complete=True,
        auto_trade_eligible=True,
        options_strategy_class="credit",
        iv_rank=65,
        options_pop=0.55,
        options_delta=0.3,
        expiration_days=28,
        defined_risk=True,
        method_tags=["iv_regime_match"],
        trade_thesis="credit in high IV",
        risks=["pin risk"],
    )
    plan = DailyTradingPlan(
        date="2026-07-14",
        overall_market_bias="Bullish",
        market_environment_score=60,
        top_watchlist=["NVDA"],
        ranked_opportunities=[opp],
        rejection_reasons=[],
        research_summary={"candidates_screened": 5, "qualified_count": 1},
        stay_in_cash=False,
    )
    text = format_research_plays(plan)
    assert "Options:" in text
    assert "IVR" in text
    assert "POP" in text
    assert "DTE" in text
    assert "defined_risk=True" in text
