"""Tests for Market Intelligence pass."""

from __future__ import annotations

from trading_agent.config import AgentConfig
from trading_agent.session.intelligence import run_intelligence_pass
from trading_agent.session.play_formatter import format_intelligence_brief

NAMED_ETFS = ("SPY", "QQQ", "IWM", "DIA", "XLK", "SMH", "SOXX", "XLF", "XLE", "XBI")

# Language that would constitute a trade ticket in the MI brief
TRADE_TICKET_BANS = (
    "Debit Call Spread",
    "buy calls",
    "buy puts",
    "position size",
    "Long Call",
    "Iron Condor",
    "strike ",
    "Approve:",
    "reduce size",
    "widen stops",
)


def test_intelligence_pass_fixture_has_bias_and_catalysts():
    config = AgentConfig(fixture_mode=True, use_live_data=False)
    brief = run_intelligence_pass(config)
    text = format_intelligence_brief(brief)

    assert brief.bias
    assert brief.environment_score > 0
    assert "Market Intelligence" in text
    assert brief.news_highlights or brief.market_signals


def test_intelligence_fixture_covers_institutional_blocks():
    config = AgentConfig(fixture_mode=True, use_live_data=False)
    brief = run_intelligence_pass(config)
    text = format_intelligence_brief(brief)

    assert 0 <= brief.environment_score <= 100
    assert brief.outlook in ("Bullish", "Bearish", "Neutral")
    assert brief.market_posture
    assert brief.sector_ranking, "expected sector ranking strongest→weakest"
    assert brief.etf_snapshot
    for etf in NAMED_ETFS:
        assert any(etf in row for row in brief.etf_snapshot), f"missing ETF {etf}"
    assert brief.top_opportunities
    assert brief.major_risks
    assert brief.expected_drivers
    assert brief.breadth_notes
    # Commodities / crypto / VIX surface in overnight or signals
    overnight_blob = " ".join(str(v) for v in brief.overnight_summary.values())
    assert "Gold" in overnight_blob or "gold" in overnight_blob.lower()
    assert "BTC" in overnight_blob or "Crypto" in text
    assert "VIX" in overnight_blob or "VIX" in text

    lower = text.lower()
    assert "market environment score" in lower
    assert "outlook" in lower
    assert "sector ranking" in lower
    assert "posture" in lower
    assert "does not recommend trades" in lower
    for banned in TRADE_TICKET_BANS:
        assert banned.lower() not in lower, f"trade language leaked: {banned}"


def test_intelligence_fixture_marks_unavailable_breadth():
    config = AgentConfig(fixture_mode=True, use_live_data=False)
    brief = run_intelligence_pass(config)
    text = format_intelligence_brief(brief)
    assert any("unavailable" in n.lower() for n in brief.breadth_notes)
    assert "TRIN" in text or any("TRIN" in n for n in brief.breadth_notes)
