"""Unit tests for Raschke first-30m 3-up + PDL day bias (shipped pure logic)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from trading_agent.analysis.day_bias import (
    apply_day_bias_tags,
    day_bias_from_rows,
    evaluate_day_bias,
    first_30m_indices,
    main as day_bias_main,
)

ET = ZoneInfo("America/New_York")


def _bars_for_session(
    session: date,
    first30_oc: list[tuple[float, float]],
    *,
    prior_low: float = 100.0,
    prior_high: float = 110.0,
    after_last: float | None = None,
) -> tuple[list, list, list, list, list]:
    """Build prior day + session first-30m (+ optional later bar)."""
    timestamps: list[datetime] = []
    opens: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []

    prior = session - timedelta(days=1)
    while prior.weekday() >= 5:
        prior -= timedelta(days=1)
    p0 = datetime(prior.year, prior.month, prior.day, 10, 0, tzinfo=ET)
    for i in range(4):
        timestamps.append(p0 + timedelta(minutes=15 * i))
        opens.append(prior_low + 2)
        highs.append(prior_high)
        lows.append(prior_low)
        closes.append(prior_low + 3)

    s0 = datetime(session.year, session.month, session.day, 9, 30, tzinfo=ET)
    for i, (o, c) in enumerate(first30_oc):
        timestamps.append(s0 + timedelta(minutes=5 * i))
        opens.append(o)
        highs.append(max(o, c) + 0.2)
        lows.append(min(o, c) - 0.2)
        closes.append(c)

    if after_last is not None:
        timestamps.append(s0 + timedelta(hours=2))
        opens.append(after_last - 0.1)
        highs.append(after_last + 0.2)
        lows.append(after_last - 0.2)
        closes.append(after_last)

    return timestamps, opens, highs, lows, closes


def test_first_30m_indices_only_in_window():
    session = date(2026, 7, 17)  # Friday
    ts = [
        datetime(2026, 7, 17, 9, 25, tzinfo=ET),
        datetime(2026, 7, 17, 9, 30, tzinfo=ET),
        datetime(2026, 7, 17, 9, 45, tzinfo=ET),
        datetime(2026, 7, 17, 10, 0, tzinfo=ET),
        datetime(2026, 7, 17, 10, 5, tzinfo=ET),
    ]
    idx = first_30m_indices(ts, session)
    assert idx == [1, 2]


def test_three_up_open_bullish_above_pdl():
    session = date(2026, 7, 17)
    ts, o, h, l, c = _bars_for_session(
        session,
        [(100.5, 101.0), (101.0, 101.5), (101.5, 102.0)],
        prior_low=100.0,
        after_last=102.5,
    )
    r = evaluate_day_bias(ts, o, h, l, c, session=session, last=102.5)
    assert r.valid
    assert r.three_up_open
    assert r.consecutive_up >= 3
    assert r.pdl == 100.0
    assert r.bias == "bullish"
    assert r.above_pdl is True
    assert "open_drive_3up" in r.tags
    assert "day_bias_bullish" in r.tags
    assert "pdl_hold" in r.tags


def test_three_up_invalidated_below_pdl():
    session = date(2026, 7, 17)
    ts, o, h, l, c = _bars_for_session(
        session,
        [(100.5, 101.0), (101.0, 101.5), (101.5, 102.0)],
        prior_low=100.0,
        after_last=99.0,
    )
    r = evaluate_day_bias(ts, o, h, l, c, session=session, last=99.0)
    assert r.three_up_open
    assert r.bias == "invalid"
    assert r.above_pdl is False
    assert "day_bias_invalid_pdl_break" in r.tags


def test_fewer_than_three_up_no_bullish():
    session = date(2026, 7, 17)
    ts, o, h, l, c = _bars_for_session(
        session,
        [(100.5, 101.0), (101.0, 101.5), (101.5, 101.2)],  # third is down
        prior_low=100.0,
        after_last=101.3,
    )
    r = evaluate_day_bias(ts, o, h, l, c, session=session, last=101.3)
    assert r.consecutive_up < 3
    assert not r.three_up_open
    assert r.bias == "neutral"
    assert "day_bias_bullish" not in r.tags


def test_fail_closed_missing_first_30m():
    session = date(2026, 7, 17)
    # only afternoon bars, no first 30m
    ts = [datetime(2026, 7, 17, 14, 0, tzinfo=ET)]
    r = evaluate_day_bias(ts, [100], [101], [99], [100.5], session=session)
    assert not r.valid
    assert r.bias == "neutral"
    assert r.note == "incomplete_first_30m_bars"


def test_fail_closed_three_up_missing_pdl():
    session = date(2026, 7, 17)
    s0 = datetime(2026, 7, 17, 9, 30, tzinfo=ET)
    ts = [s0 + timedelta(minutes=5 * i) for i in range(3)]
    o = [100.0, 101.0, 102.0]
    c = [101.0, 102.0, 103.0]
    h = [x + 0.2 for x in c]
    l = [x - 0.2 for x in o]
    r = evaluate_day_bias(ts, o, h, l, c, session=session, last=103.0)
    assert r.three_up_open
    assert not r.valid
    assert r.bias == "neutral"
    assert "missing_pdl" in r.note


def test_three_down_bearish_below_pdh():
    session = date(2026, 7, 17)
    ts, o, h, l, c = _bars_for_session(
        session,
        [(105.0, 104.0), (104.0, 103.0), (103.0, 102.0)],
        prior_low=100.0,
        prior_high=110.0,
        after_last=101.5,
    )
    r = evaluate_day_bias(ts, o, h, l, c, session=session, last=101.5)
    assert r.three_down_open
    assert r.bias == "bearish"
    assert "day_bias_bearish" in r.tags
    assert "pdh_hold" in r.tags


def test_apply_day_bias_tags_boost_aligned():
    session = date(2026, 7, 17)
    ts, o, h, l, c = _bars_for_session(
        session,
        [(100.5, 101.0), (101.0, 101.5), (101.5, 102.0)],
        prior_low=100.0,
        after_last=102.5,
    )
    r = evaluate_day_bias(ts, o, h, l, c, session=session, last=102.5)
    tags, note, boost = apply_day_bias_tags([], r, direction="bullish")
    assert "open_drive_3up" in tags
    assert boost > 0
    assert "PDL" in note or "pdl" in note.lower() or "3 consecutive" in note


def test_day_bias_main_fixture_exit_0():
    assert day_bias_main([]) == 0


def test_day_bias_from_rows_roundtrip():
    session = date(2026, 7, 17)
    ts, o, h, l, c = _bars_for_session(
        session,
        [(100.5, 101.0), (101.0, 101.5), (101.5, 102.0)],
        prior_low=99.5,
        after_last=102.0,
    )
    rows = [
        {"ts": t, "open": oo, "high": hh, "low": ll, "close": cc}
        for t, oo, hh, ll, cc in zip(ts, o, h, l, c)
    ]
    r = day_bias_from_rows(rows, session=session, last=102.0)
    assert r.bias == "bullish"
    assert r.pdl == 99.5

def test_export_applies_day_bias_tags():
    from trading_agent.analysis.day_bias import DayBiasResult
    from trading_agent.export.auto_trade_book import build_auto_trade_book
    from trading_agent.models import DailyTradingPlan, TradeOpportunity
    from tests.test_fundamentals_and_export import _opts, _tech

    good = TradeOpportunity(
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
        technical=_tech(),
        options=_opts(),
        direction="Bullish",
        setup_grade="A",
        checklist_passed=True,
        edge_complete=True,
        fundamental_score=70,
        combined_quality_score=75,
        auto_trade_eligible=True,
        defined_risk=True,
        method_tags=["predefined_risk"],
    )
    db = DayBiasResult(
        bias="bullish",
        consecutive_up=3,
        three_up_open=True,
        pdl=7548.25,
        last=7560.0,
        above_pdl=True,
        valid=True,
        tags=["open_drive_3up", "day_bias_bullish", "pdl_hold"],
        note="3 consecutive up bars; PDL hold",
    )
    plan = DailyTradingPlan(
        date="2026-07-17",
        overall_market_bias="Bullish",
        market_environment_score=66,
        top_watchlist=["NVDA"],
        ranked_opportunities=[good],
        rejection_reasons=[],
        research_summary={},
        stay_in_cash=False,
        day_bias=db,
    )
    book = build_auto_trade_book(plan, min_grade="B", min_fundamental_score=0, min_quality_score=0)
    assert book["entry_count"] == 1
    entry = book["entries"][0]
    assert "open_drive_3up" in entry["method_tags"]
    assert "day_bias_bullish" in entry["method_tags"]
    assert entry["day_bias"] == "bullish"
    assert entry["day_bias_pdl"] == 7548.25
    assert entry["day_bias_consecutive_up"] == 3
    assert book.get("day_bias", {}).get("bias") == "bullish"
    assert float(entry.get("priority_boost") or 0) >= 8.0
