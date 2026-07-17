"""Discovery refresh schedule + due-slot logic (Pacific Time)."""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from unittest.mock import MagicMock, patch

from trading_agent.models import DailyTradingPlan, RejectedSetup
from trading_agent.session.discovery import (
    due_discovery_slots,
    format_discovery_refresh,
    run_discovery_refresh,
)
from trading_agent.session.schedule import (
    DESK_CLOSE_PT,
    DESK_OPEN_PT,
    DISCOVERY_REFRESH_TIMES_PT,
    PT,
    compute_desk_schedule,
)


def test_discovery_slots_are_three_pt_times_during_rth():
    assert DISCOVERY_REFRESH_TIMES_PT == (time(7, 0), time(9, 30), time(11, 0))
    schedule = compute_desk_schedule(date(2026, 7, 14), interval_minutes=15)
    assert len(schedule.discovery_refreshes) == 3
    times = [d.time() for d in schedule.discovery_refreshes]
    assert times == list(DISCOVERY_REFRESH_TIMES_PT)
    for slot in schedule.discovery_refreshes:
        assert schedule.market_open < slot < schedule.market_close
        assert slot.tzinfo == PT


def test_schedule_log_lists_discovery():
    schedule = compute_desk_schedule(date(2026, 7, 14), interval_minutes=30)
    from trading_agent.session.schedule import render_desk_schedule_log

    text = render_desk_schedule_log(schedule, 30)
    assert "Discovery refresh" in text
    assert "07:00" in text
    assert "09:30" in text
    assert "11:00" in text
    assert "10:00" in text  # ET for 07:00 PT


def test_due_discovery_slots_skips_completed_and_future():
    schedule = compute_desk_schedule(date(2026, 7, 14), interval_minutes=15)
    slots = schedule.discovery_refreshes
    # 08:00 PT — only 07:00 due
    now = datetime(2026, 7, 14, 8, 0, tzinfo=PT)
    due = due_discovery_slots(slots, now=now, already_run=set())
    assert len(due) == 1
    assert due[0].time() == time(7, 0)

    due2 = due_discovery_slots(slots, now=now, already_run={"07:00"})
    assert due2 == []

    # 12:00 PT — all three due if none run
    late = datetime(2026, 7, 14, 12, 0, tzinfo=PT)
    due3 = due_discovery_slots(slots, now=late, already_run=set())
    assert len(due3) == 3


def test_format_discovery_refresh_mentions_slot():
    from trading_agent.session.discovery import DiscoveryRefreshResult

    msg = format_discovery_refresh(
        DiscoveryRefreshResult(
            slot_label="07:00 PT",
            scheduled_at="2026-07-14 07:00 PDT",
            candidates_screened=40,
            opportunities=2,
            watchlist=["NVDA", "AAPL"],
            new_symbols=["AMD"],
            dropped_symbols=["TLT"],
        )
    )
    assert "Discovery refresh" in msg
    assert "07:00" in msg
    assert "AMD" in msg
    assert "40" in msg
    assert "morning CIO" in msg.lower() or "capital plan" in msg.lower()


def test_should_promote_to_cio_after_cash_morning():
    from trading_agent.session.discovery import should_promote_to_cio
    from trading_agent.models import TradeOpportunity, TechnicalAnalysis, OptionsMetrics

    tech = TechnicalAnalysis(
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
    )
    opts = OptionsMetrics(
        symbol="NVDA",
        implied_volatility=30,
        iv_rank=40,
        iv_percentile=40,
        expected_move_pct=2,
        delta=0.5,
        gamma=0.05,
        theta=-0.05,
        vega=0.1,
        unusual_activity=False,
        institutional_flow_bias="bullish",
        liquidity_score=70,
        probability_of_profit=0.55,
    )
    opp = TradeOpportunity(
        rank=1,
        symbol="NVDA",
        strategy="Long Call",
        entry_price=100,
        strike_prices=[105],
        expiration="2026-08-01",
        profit_target=110,
        stop_loss=95,
        maximum_risk=200,
        maximum_reward=400,
        probability_of_success=0.55,
        confidence_score=70,
        supporting_reasons=[],
        technical=tech,
        options=opts,
        direction="Bullish",
        setup_grade="A",
        checklist_passed=True,
        edge_complete=True,
    )
    plan = DailyTradingPlan(
        date="2026-07-17",
        overall_market_bias="Bullish",
        market_environment_score=60.0,
        top_watchlist=["NVDA"],
        ranked_opportunities=[opp],
        rejection_reasons=[],
        research_summary={},
        stay_in_cash=False,
    )
    assert should_promote_to_cio(
        prior_stay_in_cash=True,
        prior_ranked_count=0,
        prior_ranked_symbols=[],
        new_plan=plan,
    )
    # No promotion when still cash / empty ranked
    cash_plan = DailyTradingPlan(
        date="2026-07-17",
        overall_market_bias="Bearish",
        market_environment_score=25.0,
        top_watchlist=["UVXY"],
        ranked_opportunities=[],
        rejection_reasons=[],
        research_summary={},
        stay_in_cash=True,
    )
    assert not should_promote_to_cio(
        prior_stay_in_cash=True,
        prior_ranked_count=0,
        prior_ranked_symbols=[],
        new_plan=cash_plan,
    )
    # No promotion when same ranked set already known
    assert not should_promote_to_cio(
        prior_stay_in_cash=False,
        prior_ranked_count=1,
        prior_ranked_symbols=["NVDA"],
        new_plan=plan,
    )


def test_discovery_promotes_cio_when_tradeable(tmp_path: Path):
    """Shipped path: cash morning → discovery with ranked opp → CIO re-eval once."""
    from trading_agent.models import (
        OptionsMetrics,
        TechnicalAnalysis,
        TradeOpportunity,
    )
    from trading_agent.session.discovery import run_discovery_refresh

    tech = TechnicalAnalysis(
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
    )
    opts = OptionsMetrics(
        symbol="NVDA",
        implied_volatility=30,
        iv_rank=40,
        iv_percentile=40,
        expected_move_pct=2,
        delta=0.5,
        gamma=0.05,
        theta=-0.05,
        vega=0.1,
        unusual_activity=False,
        institutional_flow_bias="bullish",
        liquidity_score=70,
        probability_of_profit=0.55,
    )
    opp = TradeOpportunity(
        rank=1,
        symbol="NVDA",
        strategy="Long Call",
        entry_price=100,
        strike_prices=[105],
        expiration="2026-08-01",
        profit_target=110,
        stop_loss=95,
        maximum_risk=200,
        maximum_reward=400,
        probability_of_success=0.55,
        confidence_score=75,
        supporting_reasons=["setup"],
        technical=tech,
        options=opts,
        direction="Bullish",
        setup_grade="A",
        checklist_passed=True,
        edge_complete=True,
        auto_trade_eligible=True,
        defined_risk=True,
    )
    plan = DailyTradingPlan(
        date="2026-07-17",
        overall_market_bias="Bullish",
        market_environment_score=65.0,
        top_watchlist=["NVDA", "AMD"],
        ranked_opportunities=[opp],
        rejection_reasons=[],
        research_summary={
            "candidates_screened": 40,
            "news_highlights": [],
            "high_impact_events": [],
        },
        stay_in_cash=False,
        cash_recommendation_reason="",
    )
    fake_report = MagicMock()
    fake_report.approved = [MagicMock(ticker="NVDA")]
    fake_report.modified = []
    fake_report.rejected = []

    with patch("trading_agent.session.discovery.run_pipeline", return_value=plan):
        with patch(
            "trading_agent.session.discovery.promote_discovery_to_cio",
            return_value={
                "approved": ["NVDA"],
                "modified": [],
                "rejected_count": 0,
                "message": "CIO Discovery Promotion — approved NVDA",
            },
        ) as promo:
            from trading_agent.config import AgentConfig

            result = run_discovery_refresh(
                AgentConfig(fixture_mode=True),
                session_dir=tmp_path,
                prior_context={
                    "top_watchlist": ["UVXY"],
                    "ranked_symbols": [],
                    "ranked_opportunities": [],
                    "stay_in_cash": True,
                    "cash_recommendation_reason": "morning cash",
                },
                slot_label="09:30 PT",
                scheduled_at=datetime(2026, 7, 17, 9, 30, tzinfo=PT),
                promote_cio=True,
                fixture_mode=True,
            )
    assert result.opportunities == 1
    assert result.cio_promoted is True
    assert "NVDA" in result.cio_approved
    promo.assert_called_once()
    msg = format_discovery_refresh(result)
    assert "CIO mid-session promotion" in msg or "promot" in msg.lower()


def test_run_discovery_refresh_merges_plan(tmp_path: Path):
    plan = DailyTradingPlan(
        date="2026-07-14",
        overall_market_bias="Bullish",
        market_environment_score=60.0,
        top_watchlist=["NVDA", "AMD"],
        ranked_opportunities=[],
        rejection_reasons=[RejectedSetup(symbol="X", reason="test")],
        research_summary={"candidates_screened": 12, "news_highlights": [], "high_impact_events": []},
        stay_in_cash=True,
        cash_recommendation_reason="no setups",
    )
    with patch("trading_agent.session.discovery.run_pipeline", return_value=plan):
        from trading_agent.config import AgentConfig

        result = run_discovery_refresh(
            AgentConfig(fixture_mode=True),
            session_dir=tmp_path,
            prior_context={"top_watchlist": ["AAPL"], "ranked_symbols": ["AAPL"]},
            slot_label="07:00 PT",
            scheduled_at=datetime(2026, 7, 14, 7, 0, tzinfo=PT),
        )
    assert result.new_symbols  # NVDA/AMD new vs AAPL
    assert "AAPL" in result.dropped_symbols
    assert (tmp_path / "daily_plan_context.json").exists()
    assert result.candidates_screened == 12
