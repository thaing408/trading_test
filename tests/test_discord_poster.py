"""Tests for Discord chunking and webhook posting."""

from __future__ import annotations

from trading_agent.discord.formatter import DISCORD_CONTENT_LIMIT, chunk_message
from trading_agent.discord.poster import post_to_discord
from trading_agent.intraday.config import IntradayConfig
from trading_agent.intraday.pipeline import run_intraday_pipeline
from trading_agent.pipeline import run_pipeline
from trading_agent.config import AgentConfig
from trading_agent.session.play_formatter import format_intraday_plays, format_premarket_plays


def test_chunk_message_splits_long_text():
    text = "A" * (DISCORD_CONTENT_LIMIT + 50)
    chunks = chunk_message(text)
    assert len(chunks) >= 2
    assert all(len(chunk) <= DISCORD_CONTENT_LIMIT for chunk in chunks)
    assert "".join(chunks).replace("\n", "") == text


def test_chunk_message_preserves_short_message():
    text = "NVDA — Hold"
    assert chunk_message(text) == [text]


def test_post_to_discord_sends_pipeline_rendered_content():
    agent = AgentConfig(fixture_mode=True, use_live_data=False)
    plan = run_pipeline(agent)
    premarket = format_premarket_plays(plan)

    intraday = IntradayConfig(fixture_mode=True, use_live_data=False)
    report = run_intraday_pipeline(intraday)
    intraday_text = format_intraday_plays(report, cycle=1)
    content = premarket + "\n\n" + intraday_text

    captured: list[dict] = []

    class FakeResponse:
        status_code = 204
        ok = True
        text = ""

    def fake_poster(url: str, payload: dict) -> FakeResponse:
        captured.append({"url": url, "payload": payload})
        return FakeResponse()

    results = post_to_discord(
        content,
        "https://discord.test/webhook",
        poster=fake_poster,
    )

    assert results[0]["status_code"] == 204
    assert captured
    body = captured[0]["payload"]["content"]
    assert any(term in body for term in ("STAY IN CASH", "Ranked plays", "NVDA", "AAPL", "TSLA"))
    assert any(term in body for term in ("Exit", "Hold", "Move Stop Loss", "Watchlist scout", "Position actions"))