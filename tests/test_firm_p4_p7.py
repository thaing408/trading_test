"""P4–P7 firm tests: risk/manager, indicators, eval, discord gate."""

from __future__ import annotations

import json
from pathlib import Path

from trading_agent.firm.discord_card import firm_discord_enabled, format_firm_card_message
from trading_agent.firm.eval import evaluate_firm_day, write_eval_report
from trading_agent.firm.indicators import build_indicator_pack
from trading_agent.firm.manager import build_manager_decision
from trading_agent.firm.protocol import FirmCard
from trading_agent.firm.reports import (
    DebateVerdict,
    FundamentalReport,
    ReportMeta,
    TechnicalReport,
    TraderProposal,
)
from trading_agent.firm.risk_debate import apply_risk_to_proposal, run_risk_debate
from trading_agent.firm.runner import run_firm_for_symbol


def test_indicator_pack_count():
    closes = [100 + i * 0.1 for i in range(120)]
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    vols = [1e6] * 120
    pack = build_indicator_pack(
        {
            "status": "ok",
            "closes": closes,
            "highs": highs,
            "lows": lows,
            "volumes": vols,
        }
    )
    assert pack["status"] == "ok"
    assert pack["count"] >= 40
    assert "rsi_14" in pack["features"]
    assert pack["features"]["breadth_ad_unavailable"] == -1.0


def test_risk_veto_on_earnings():
    day = "2026-08-17"
    prop = TraderProposal(
        meta=ReportMeta("AAPL", day, "trader", status="stub"),
        action="BUY",
        side="Bullish",
        confidence=80,
        size_hint="full",
        thesis="buy",
    )
    tech = TechnicalReport(
        meta=ReportMeta("AAPL", day, "technical_analyst", status="stub"),
        bias="bullish",
        regime="uptrend",
        indicator_highlights=["ADX=25"],
    )
    fund = FundamentalReport(
        meta=ReportMeta("AAPL", day, "fundamental_analyst", status="stub"),
        fundamental_score=70,
        reasons=["Earnings in 1d (2026-08-18) — event risk (-20)"],
    )
    debate = DebateVerdict(
        meta=ReportMeta("AAPL", day, "debate_facilitator", status="stub"),
        winner="bull",
        confidence=70,
    )
    risk = run_risk_debate(
        symbol="AAPL",
        trading_date=day,
        prop=prop,
        tech=tech,
        fund=fund,
        debate=debate,
        use_llm=False,
        exposure={"open_lots": 1, "open_risk": 100},
    )
    assert risk.recommendation == "veto"
    assert risk.hard_rails_respected
    prop2 = apply_risk_to_proposal(prop, risk)
    assert prop2.action == "HOLD"
    mgr = build_manager_decision(
        symbol="AAPL",
        trading_date=day,
        prop=prop2,
        risk=risk,
        debate=debate,
        use_llm=False,
    )
    assert mgr.decision == "reject"
    assert mgr.cites_debate_winner == "bull"


def test_eval_and_discord_format(tmp_path):
    day = "2026-08-17"
    firm = tmp_path / day / "firm" / "AAPL"
    firm.mkdir(parents=True)
    (firm / "trader_proposal.json").write_text(
        json.dumps({"action": "BUY", "confidence": 70, "side": "Bullish"}),
        encoding="utf-8",
    )
    (firm / "debate_verdict.json").write_text(
        json.dumps({"winner": "bull"}), encoding="utf-8"
    )
    (firm / "risk_adjustment.json").write_text(
        json.dumps({"recommendation": "unchanged"}), encoding="utf-8"
    )
    (firm / "manager_decision.json").write_text(
        json.dumps({"decision": "approve"}), encoding="utf-8"
    )
    book = tmp_path / "book.json"
    book.write_text(
        json.dumps({"entries": [{"symbol": "AAPL", "action": "ENTER"}]}),
        encoding="utf-8",
    )
    rep = evaluate_firm_day(day, session_root=tmp_path, book_path=book)
    assert rep.n_symbols == 1
    assert rep.n_buy == 1
    assert rep.agreement_rate == 1.0
    path = write_eval_report(rep, session_root=tmp_path)
    assert path.is_file()

    card = FirmCard(
        symbol="AAPL",
        trading_date=day,
        trader_action="BUY",
        debate_winner="bull",
        risk_adjustment="unchanged",
        manager_decision="approve",
        status="p4_manager",
    )
    text = format_firm_card_message(card)
    assert "Firm card — AAPL" in text
    assert "BUY" in text


def test_runner_p4_fields(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_AGENT_FIRM", "0")
    monkeypatch.setenv("TRADING_AGENT_FIRM_LLM", "0")
    monkeypatch.setenv("TRADING_AGENT_FIRM_DISCORD", "0")
    monkeypatch.setenv("TRADING_AGENT_FIRM_BOOK_MERGE", "0")

    fake = {
        "ohlcv": {
            "status": "ok",
            "last": 190.0,
            "closes": [180.0 + i for i in range(80)],
            "highs": [181.0 + i for i in range(80)],
            "lows": [179.0 + i for i in range(80)],
            "volumes": [1e6] * 80,
            "change_pct": 0.5,
            "n": 80,
        },
        "ta_bundle": {
            "status": "ok",
            "last": 190.0,
            "rsi14": 55,
            "macd": "bullish",
            "ma_alignment": "bullish",
            "bollinger": "middle",
            "atr14": 3.0,
            "adx14": 22,
            "support_resistance": [180, 195],
            "regime": "uptrend",
            "bias": "bullish",
            "change_pct": 0.5,
            "indicator_count": 50,
            "indicator_pack": {"status": "ok", "count": 50, "features": {}},
        },
        "news": {
            "status": "ok",
            "source": "test",
            "items": [{"headline": "AAPL beats estimates", "category": "earnings"}],
        },
        "fundamentals": {
            "status": "ok",
            "score": 80.0,
            "passed": True,
            "reasons": ["Large-cap"],
            "pe_ttm": 30,
            "forward_pe": 28,
            "market_cap": 1e12,
            "profit_margin": 0.2,
            "revenue_growth": 0.08,
            "debt_to_equity": 50,
            "sector": "Tech",
            "source": "test",
        },
        "insider": {"status": "empty", "items": []},
        "social": {
            "status": "ok",
            "score": 15,
            "tilt": "bullish",
            "peaks": ["+beat"],
            "engagement_notes": "proxy",
            "source": "news_tone_proxy",
        },
    }

    def fake_call(name, *, symbol, **kwargs):
        from trading_agent.firm.tools import ToolResult

        return ToolResult(tool=name, ok=True, data=fake.get(name) or {"status": "empty"})

    monkeypatch.setattr("trading_agent.firm.runner.call_tool", fake_call)
    monkeypatch.setattr("trading_agent.firm.react.call_tool", fake_call)
    monkeypatch.setattr(
        "trading_agent.firm.runner.gather_calendar",
        lambda sym: {"status": "unavailable", "events": []},
    )
    monkeypatch.setattr(
        "trading_agent.firm.risk_debate._oms_exposure_snapshot",
        lambda: {"open_lots": 1, "open_risk": 100.0, "symbols": ["X"]},
    )

    out = run_firm_for_symbol(
        "AAPL",
        trading_date="2026-08-17",
        session_root=tmp_path,
        force=True,
        use_llm=False,
    )
    assert out["ok"]
    assert "risk" in out and "manager" in out
    assert out["manager"]["decision"] in ("approve", "modify", "reject", "defer")
    d = Path(out["path"])
    assert (d / "risk_adjustment.json").is_file()
    assert (d / "manager_decision.json").is_file()
    assert (d / "data_pack.json").is_file()
    card = json.loads((d / "firm_card.json").read_text())
    assert card["status"] == "p4_manager"
