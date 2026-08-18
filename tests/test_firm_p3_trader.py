"""P3 firm trader tests."""

from __future__ import annotations

import json
from pathlib import Path

from trading_agent.firm.reports import (
    DebateVerdict,
    FundamentalReport,
    NewsReport,
    ReportMeta,
    SentimentReport,
    TechnicalReport,
)
from trading_agent.firm.trader import (
    book_merge_enabled,
    build_trader_proposal,
    maybe_merge_proposal_into_book,
    proposal_to_book_fields,
)


def _reports_bullish():
    day = "2026-08-17"
    tech = TechnicalReport(
        meta=ReportMeta("AAPL", day, "technical_analyst", status="stub"),
        regime="uptrend",
        bias="bullish",
        entry_timing="on_pullback",
        exit_timing="trail",
    )
    news = NewsReport(
        meta=ReportMeta("AAPL", day, "news_analyst", status="stub"),
        name_catalysts=["AAPL beats estimates"],
        headlines=["AAPL beats estimates"],
    )
    fund = FundamentalReport(
        meta=ReportMeta("AAPL", day, "fundamental_analyst", status="stub"),
        fundamental_score=80.0,
        reasons=["Large-cap"],
    )
    sent = SentimentReport(
        meta=ReportMeta("AAPL", day, "sentiment_analyst", status="stub"),
        score=20.0,
        tilt="bullish",
    )
    debate = DebateVerdict(
        meta=ReportMeta("AAPL", day, "debate_facilitator", status="stub"),
        winner="bull",
        confidence=70.0,
        rounds=2,
        bull_points=["Uptrend intact"],
        bear_points=["Macro tariff risk"],
        open_risks=["advisory_only_hard_rails_still_apply"],
        summary="bull wins",
    )
    return tech, news, fund, sent, debate


def test_trader_buy_on_bull_debate():
    tech, news, fund, sent, debate = _reports_bullish()
    prop = build_trader_proposal(
        symbol="AAPL",
        trading_date="2026-08-17",
        tech=tech,
        news=news,
        fund=fund,
        sent=sent,
        debate=debate,
        geometry={
            "entry": 190.0,
            "stop": 185.0,
            "target": 200.0,
            "strike_prices": [195.0],
            "expiration": "2026-08-21",
            "dte": 4,
            "max_risk_dollars": 200,
        },
        use_llm=False,
    )
    assert prop.action == "BUY"
    assert prop.side == "Bullish"
    assert prop.confidence >= 55
    assert "debate" in prop.thesis.lower() or "Bull" in prop.thesis
    assert prop.book_hints["mapped_action"] == "ENTER"
    assert prop.book_hints["geometry"]["expiration"] == "2026-08-21"
    fields = proposal_to_book_fields(prop)
    assert fields["action"] == "ENTER"
    assert fields["source"] == "firm_trader"
    assert fields["auto_trade_eligible"] is True


def test_trader_hold_on_draw_weak():
    tech, news, fund, sent, debate = _reports_bullish()
    tech.bias = "neutral"
    tech.regime = "range_or_mixed"
    fund.fundamental_score = 50
    sent.tilt = "neutral"
    debate.winner = "draw"
    debate.confidence = 42
    prop = build_trader_proposal(
        symbol="AAPL",
        trading_date="2026-08-17",
        tech=tech,
        news=news,
        fund=fund,
        sent=sent,
        debate=debate,
        use_llm=False,
    )
    assert prop.action == "HOLD"
    fields = proposal_to_book_fields(prop)
    assert fields["auto_trade_eligible"] is False


def test_book_merge_hold(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_AGENT_FIRM_BOOK_MERGE", "1")
    assert book_merge_enabled()
    book = {
        "entries": [
            {
                "symbol": "AAPL",
                "action": "ENTER",
                "side": "Bullish",
                "auto_trade_eligible": True,
                "notes": "multi",
            }
        ],
        "entry_count": 1,
    }
    path = tmp_path / "auto_trade_book.json"
    path.write_text(json.dumps(book), encoding="utf-8")

    tech, news, fund, sent, debate = _reports_bullish()
    debate.winner = "draw"
    debate.confidence = 40
    tech.bias = "neutral"
    prop = build_trader_proposal(
        symbol="AAPL",
        trading_date="2026-08-17",
        tech=tech,
        news=news,
        fund=fund,
        sent=sent,
        debate=debate,
        use_llm=False,
    )
    assert prop.action == "HOLD"
    res = maybe_merge_proposal_into_book(prop, book_path=path)
    assert res.get("ok") and res.get("merged")
    data = json.loads(path.read_text())
    assert data["entries"][0]["auto_trade_eligible"] is False
    assert data["entries"][0]["firm_action"] == "HOLD"
