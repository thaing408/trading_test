"""P2 bull/bear debate tests (no LLM)."""

from __future__ import annotations

import json
from pathlib import Path

from trading_agent.firm.debate import (
    bear_opening_points,
    bull_opening_points,
    debate_rounds,
    run_debate,
)
from trading_agent.firm.reports import (
    FundamentalReport,
    NewsReport,
    ReportMeta,
    SentimentReport,
    TechnicalReport,
)
from trading_agent.firm.runner import run_firm_for_symbol


def _tech(**kw):
    base = dict(
        meta=ReportMeta("AAPL", "2026-08-17", "technical_analyst", status="stub"),
        regime="uptrend",
        bias="bullish",
        entry_timing="pullback",
        exit_timing="trail",
        method_conflicts=[],
        indicator_highlights=["RSI14=55"],
        reasons=["ok"],
    )
    base.update(kw)
    return TechnicalReport(**base)


def _fund(**kw):
    base = dict(
        meta=ReportMeta("AAPL", "2026-08-17", "fundamental_analyst", status="stub"),
        fundamental_score=80.0,
        reasons=["Large-cap"],
        valuation_summary="PE=30",
        quality_summary="margins ok",
        leverage_summary="D/E=50",
        earnings_risk="days_to=40",
    )
    base.update(kw)
    return FundamentalReport(**base)


def _news(**kw):
    base = dict(
        meta=ReportMeta("AAPL", "2026-08-17", "news_analyst", status="stub"),
        name_catalysts=["AAPL beats estimates"],
        headlines=["AAPL beats estimates"],
        macro_catalysts=[],
    )
    base.update(kw)
    return NewsReport(**base)


def _sent(**kw):
    base = dict(
        meta=ReportMeta("AAPL", "2026-08-17", "sentiment_analyst", status="stub"),
        score=20.0,
        tilt="bullish",
        peaks=["+beat"],
    )
    base.update(kw)
    return SentimentReport(**base)


def test_bull_bear_opening_points():
    bull = bull_opening_points(_tech(), _news(), _fund(), _sent())
    bear = bear_opening_points(
        _tech(bias="bearish", regime="downtrend", method_conflicts=["ma_conflict"]),
        _news(name_catalysts=["AAPL faces lawsuit"], headlines=["AAPL faces lawsuit"]),
        _fund(fundamental_score=40.0, reasons=["Earnings in 1d — event risk (-20)"]),
        _sent(tilt="bearish", score=-20),
    )
    assert bull and any("Technical" in p or "Fundamental" in p or "Sentiment" in p or "Catalyst" in p for p in bull)
    assert bear and any("lawsuit" in p.lower() or "Weak" in p or "Event" in p or "Conflict" in p for p in bear)


def test_run_debate_bullish_lean(monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_FIRM_DEBATE_ROUNDS", "2")
    monkeypatch.setenv("TRADING_AGENT_FIRM_LLM", "0")
    verdict, transcript = run_debate(
        symbol="AAPL",
        trading_date="2026-08-17",
        tech=_tech(),
        news=_news(),
        fund=_fund(),
        sent=_sent(),
        use_llm=False,
        n_rounds=2,
    )
    assert verdict.rounds == 2
    assert verdict.winner in ("bull", "bear", "draw")
    assert verdict.bull_points and verdict.bear_points
    assert "advisory_only_hard_rails_still_apply" in verdict.open_risks
    assert verdict.meta.status in ("stub", "complete")
    assert any(t.get("role") == "debate_facilitator" for t in transcript)


def test_debate_rounds_env(monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_FIRM_DEBATE_ROUNDS", "3")
    assert debate_rounds() == 3


def test_runner_includes_debate(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_AGENT_FIRM", "0")
    monkeypatch.setenv("TRADING_AGENT_FIRM_LLM", "0")
    monkeypatch.setenv("TRADING_AGENT_FIRM_DEBATE_ROUNDS", "2")

    fake = {
        "ohlcv": {
            "status": "ok", "last": 190.0, "closes": [180.0 + i for i in range(60)],
            "highs": [181.0 + i for i in range(60)], "lows": [179.0 + i for i in range(60)],
            "volumes": [1e6] * 60, "change_pct": 0.5, "n": 60,
        },
        "ta_bundle": {
            "status": "ok", "last": 190.0, "rsi14": 55, "macd": "bullish",
            "ma_alignment": "bullish", "bollinger": "middle", "atr14": 3.0,
            "adx14": 22, "support_resistance": [180, 195], "regime": "uptrend",
            "bias": "bullish", "change_pct": 0.5,
        },
        "news": {
            "status": "ok", "source": "test",
            "items": [{"headline": "AAPL beats estimates", "category": "earnings"}],
        },
        "fundamentals": {
            "status": "ok", "score": 80.0, "passed": True, "reasons": ["Large-cap"],
            "pe_ttm": 30, "forward_pe": 28, "market_cap": 1e12,
            "profit_margin": 0.2, "revenue_growth": 0.08, "debt_to_equity": 50,
            "sector": "Tech", "earnings_date": "", "days_to_earnings": None,
            "source": "test",
        },
        "insider": {"status": "empty", "items": []},
        "social": {
            "status": "ok", "score": 15, "tilt": "bullish", "peaks": ["+beat"],
            "engagement_notes": "proxy", "source": "news_tone_proxy",
        },
    }

    def fake_call(name, *, symbol, **kwargs):
        from trading_agent.firm.tools import ToolResult

        return ToolResult(tool=name, ok=True, data=fake.get(name) or {"status": "empty"})

    monkeypatch.setattr("trading_agent.firm.runner.call_tool", fake_call)
    monkeypatch.setattr("trading_agent.firm.react.call_tool", fake_call)

    out = run_firm_for_symbol(
        "AAPL",
        trading_date="2026-08-17",
        session_root=tmp_path,
        force=True,
        use_llm=False,
    )
    assert out["ok"]
    assert out["debate"]["winner"] in ("bull", "bear", "draw")
    assert out["debate"]["rounds"] == 2
    d = Path(out["path"])
    deb = json.loads((d / "debate_verdict.json").read_text())
    assert deb["winner"] == out["debate"]["winner"]
    assert (d / "debate_transcript.json").is_file()
    card = json.loads((d / "firm_card.json").read_text())
    assert card["status"] == "p2_debate"
    assert card["debate_winner"] == out["debate"]["winner"]
