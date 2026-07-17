"""Intraday Discord: meaningful titles + suppress repeat cycle spam."""

from __future__ import annotations

from trading_agent.intraday.models import (
    Alert,
    IntradayReport,
    PositionRecommendation,
    RiskLimitEvaluation,
    SessionSnapshot,
    SessionSynthesis,
)
from trading_agent.session.play_formatter import (
    format_intraday_discord_title,
    format_intraday_plays,
    intraday_cycle_fingerprint,
    should_post_intraday_discord,
    summarize_intraday_actions,
)


def _report(
    *,
    recs: list[tuple[str, str]] | None = None,
    alerts: list[tuple[str, str, str]] | None = None,
    no_open: bool = False,
    regime_shift: bool = False,
) -> IntradayReport:
    recommendations = [
        PositionRecommendation(
            symbol=sym,
            action=action,
            what_changed="",
            why_recommended=f"{action} reason",
            risk_if_no_action="",
            updated_probability=0.5,
            updated_confidence=60.0,
        )
        for sym, action in (recs or [])
    ]
    notifications = [
        Alert(
            alert_type=atype,
            symbol=sym,
            message=msg,
            recommended_response=msg,
            severity=sev,
        )
        for sym, atype, sev, msg in [
            (a[0], a[1], a[2], a[1]) for a in (alerts or [])
        ]
    ]
    return IntradayReport(
        timestamp="2026-07-16 13:33 UTC",
        cycle_count=1,
        session=SessionSynthesis(
            regime_shift=regime_shift,
            regime_description="Session regime is neutral",
            observations=[],
            risk_environment="normal",
            session_score=58.0,
        ),
        session_snapshot=SessionSnapshot(
            source="test",
            market_regime="neutral",
            prior_regime="neutral",
            vix=16.0,
            vix_change_pct=0.0,
            breadth_advancers=1,
            breadth_decliners=1,
            breadth_ratio=1.0,
            sector_leaders=[],
            sector_laggards=[],
        ),
        recommendations=recommendations,
        notifications=notifications,
        risk_evaluation=RiskLimitEvaluation(within_limits=True),
        no_open_positions=no_open,
        plan_context={"top_watchlist": []},
    )


def test_summary_prefers_exits_over_cycle_number():
    r = _report(recs=[("QS", "Exit"), ("ORCL", "Take Partial Profit"), ("AAPL", "Hold")])
    assert summarize_intraday_actions(r) == "Exit · Partial"
    title = format_intraday_discord_title(r, 42)
    assert "cycle" not in title.lower()
    assert "Exit" in title
    assert "Partial" in title


def test_fingerprint_ignores_holds_and_suppresses_repeats():
    a = _report(recs=[("QS", "Exit"), ("AAPL", "Hold")])
    b = _report(recs=[("QS", "Exit"), ("AAPL", "Hold")])  # same actions
    c = _report(recs=[("QS", "Exit"), ("ORCL", "Take Partial Profit")])
    assert intraday_cycle_fingerprint(a) == intraday_cycle_fingerprint(b)
    assert intraday_cycle_fingerprint(a) != intraday_cycle_fingerprint(c)

    post1, fp1 = should_post_intraday_discord(a, cycle=1, previous_fingerprint=None)
    assert post1 is True
    post2, fp2 = should_post_intraday_discord(b, cycle=2, previous_fingerprint=fp1)
    assert post2 is False
    assert fp2 == fp1
    post3, _ = should_post_intraday_discord(c, cycle=3, previous_fingerprint=fp2)
    assert post3 is True


def test_flat_watchlist_posts_once():
    flat = _report(no_open=True)
    post1, fp = should_post_intraday_discord(flat, cycle=1, previous_fingerprint=None)
    post2, _ = should_post_intraday_discord(flat, cycle=2, previous_fingerprint=fp)
    assert post1 is True
    assert post2 is False


def test_format_header_not_bare_cycle():
    r = _report(recs=[("QS", "Exit")])
    text = format_intraday_plays(r, cycle=7)
    assert "cycle 7" not in text.lower() or "check #7" in text
    assert "**Trading Desk · Exit**" in text
    assert "check #7" in text
