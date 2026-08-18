"""P1 firm analysts — heuristics without network/LLM."""

from __future__ import annotations

import json
from pathlib import Path

from trading_agent.firm.analysts import (
    build_fundamental_report,
    build_news_report,
    build_sentiment_report,
    build_technical_report,
)
from trading_agent.firm.runner import run_firm_for_symbol


def test_technical_heuristic():
    ta = {
        "status": "ok",
        "last": 100.0,
        "change_pct": 1.2,
        "rsi14": 62.0,
        "macd": "bullish",
        "ma_alignment": "bullish",
        "bollinger": "upper",
        "atr14": 2.1,
        "adx14": 28.0,
        "support_resistance": [95.0, 105.0],
        "regime": "uptrend",
        "bias": "bullish",
    }
    r = build_technical_report("AAPL", "2026-08-17", ta, use_llm=False)
    assert r.meta.status == "stub"
    assert r.bias == "bullish"
    assert r.regime == "uptrend"
    assert any("RSI" in h for h in r.indicator_highlights)


def test_news_heuristic():
    news = {
        "status": "ok",
        "source": "fixture",
        "items": [
            {"headline": "AAPL unveils new product", "category": "general"},
            {"headline": "Fed holds rates steady", "category": "geopolitical"},
        ],
    }
    r = build_news_report("AAPL", "2026-08-17", news, use_llm=False)
    assert r.meta.status == "stub"
    assert r.headlines
    assert r.name_catalysts or r.macro_catalysts


def test_fundamental_heuristic_fills_score():
    fund = {
        "status": "ok",
        "score": 72.0,
        "passed": True,
        "reasons": ["Large-cap (+8)"],
        "pe_ttm": 28.0,
        "forward_pe": 25.0,
        "market_cap": 3e12,
        "profit_margin": 0.25,
        "revenue_growth": 0.1,
        "debt_to_equity": 80.0,
        "sector": "Technology",
        "earnings_date": "2026-10-01",
        "days_to_earnings": 45,
        "source": "yfinance",
    }
    r = build_fundamental_report("AAPL", "2026-08-17", fund, use_llm=False)
    assert r.fundamental_score == 72.0
    assert r.meta.status == "stub"
    assert "PE=" in r.valuation_summary


def test_sentiment_news_tone_proxy():
    social = {
        "status": "ok",
        "score": 20.0,
        "tilt": "bullish",
        "peaks": ["+surge"],
        "engagement_notes": "news_tone_proxy n=3",
        "source": "news_tone_proxy",
    }
    r = build_sentiment_report("AAPL", "2026-08-17", social, use_llm=False)
    assert r.tilt == "bullish"
    assert r.score == 20.0


def test_runner_p1_with_mocked_tools(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_AGENT_FIRM", "0")
    monkeypatch.setenv("TRADING_AGENT_FIRM_LLM", "0")

    fake = {
        "ohlcv": {"status": "ok", "last": 190.0, "closes": [180 + i for i in range(60)],
                  "highs": [181 + i for i in range(60)], "lows": [179 + i for i in range(60)],
                  "volumes": [1e6] * 60, "change_pct": 0.5, "n": 60},
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
            "status": "ok", "score": 68.0, "passed": True, "reasons": ["ok"],
            "pe_ttm": 30, "forward_pe": 28, "market_cap": 1e12,
            "profit_margin": 0.2, "revenue_growth": 0.08, "debt_to_equity": 50,
            "sector": "Tech", "earnings_date": "", "days_to_earnings": None,
            "source": "test",
        },
        "insider": {"status": "empty", "items": []},
        "social": {
            "status": "ok", "score": 10, "tilt": "bullish", "peaks": ["+beat"],
            "engagement_notes": "proxy", "source": "news_tone_proxy",
        },
    }

    def fake_call(name, *, symbol, **kwargs):
        from trading_agent.firm.tools import ToolResult

        data = fake.get(name) or {"status": "empty"}
        return ToolResult(tool=name, ok=True, data=data, stub=False)

    monkeypatch.setattr("trading_agent.firm.runner.call_tool", fake_call)
    monkeypatch.setattr("trading_agent.firm.react.call_tool", fake_call)

    out = run_firm_for_symbol(
        "AAPL",
        trading_date="2026-08-17",
        session_root=tmp_path,
        force=True,
        use_llm=False,
    )
    assert out["ok"] and out["analyst_status"]["fundamental_score"] == 68.0
    d = Path(out["path"])
    tech = json.loads((d / "technical_report.json").read_text())
    assert tech["bias"] == "bullish"
    assert tech["meta"]["status"] in ("stub", "complete")
    fund = json.loads((d / "fundamental_report.json").read_text())
    assert fund["fundamental_score"] == 68.0
    card = json.loads((d / "firm_card.json").read_text())
    assert card["status"] == "p4_manager"
