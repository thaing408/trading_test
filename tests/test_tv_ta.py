"""TradingView TA enrich (P1+P2) — unit tests without live network."""

from __future__ import annotations

from trading_agent.research import tv_ta as tv


def test_tv_ta_disabled_by_default(monkeypatch):
    monkeypatch.delenv("TRADING_AGENT_TV_TA", raising=False)
    assert tv.tv_ta_enabled() is False
    pack = tv.enrich_symbols(["AAPL"])
    assert pack.get("skipped") is True


def test_bb_sigma_ratings():
    # mid=100, upper=110, lower=90 → half=10 → σ_unit=5
    z, rating = tv.bb_sigma_and_rating(100.0, 110.0, 90.0)
    assert z == 0.0
    assert rating == "INSIDE"
    z2, r2 = tv.bb_sigma_and_rating(115.0, 110.0, 90.0)  # +3σ
    assert z2 == 3.0
    assert r2 == "EXT_PLUS3"
    z3, r3 = tv.bb_sigma_and_rating(85.0, 110.0, 90.0)  # -3σ
    assert z3 == -3.0
    assert r3 == "EXT_MINUS3"
    z4, r4 = tv.bb_sigma_and_rating(107.0, 110.0, 90.0)  # +1.4σ → NEAR_UPPER
    assert r4 == "NEAR_UPPER"


def test_enrich_force_uses_mock(monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_TV_TA", "0")

    def fake_screener(symbols, **kwargs):
        return [
            {
                "symbol": str(s).upper(),
                "recommendation": "BUY",
                "buy": 10,
                "sell": 2,
                "neutral": 5,
                "oscillators": "NEUTRAL",
                "moving_averages": "BUY",
                "close": 100.0,
                "rsi": 55.0,
                "bb_sigma": 0.0,
                "bb_rating": "INSIDE",
                "error": "",
                "source": "tradingview_screener",
            }
            for s in symbols
        ]

    monkeypatch.setattr(tv, "_enrich_via_screener", fake_screener)
    pack = tv.enrich_symbols(["aapl", "msft"], force=True, throttle=0)
    assert pack["skipped"] is False
    assert pack["count"] == 2
    assert pack["ok_count"] == 2
    assert pack["symbols"][0]["recommendation"] == "BUY"
    text = tv.format_tv_ta_report(pack)
    assert "AAPL" in text
    assert "BUY" in text
    assert "```" in text  # Discord code fence, not markdown table
    fence = text.split("```")[1]
    assert "|" not in fence  # no pipe tables inside fence


def test_format_rounds_and_hides_errors():
    pack = {
        "interval": "1d",
        "generated_at": "2026-08-20T00:00:00+00:00",
        "ok_count": 1,
        "error_count": 1,
        "symbols": [
            {
                "symbol": "QQQ",
                "recommendation": "STRONG_BUY",
                "buy": 13,
                "sell": 3,
                "neutral": 10,
                "oscillators": "BUY",
                "moving_averages": "STRONG_BUY",
                "bb_rating": "INSIDE",
                "bb_sigma": 0.449123,
                "rsi": 51.450508,
            },
            {"symbol": "AAPL", "error": "Can't access TradingView's API. HTTP sta"},
        ],
    }
    text = tv.format_tv_ta_report(pack)
    assert "0.45" in text
    assert "51.5" in text
    assert "0.449123" not in text
    assert "AAPL" not in text.split("```")[1]  # errors not in main grid
    assert "Failed" in text and "AAPL" in text


def test_fmt_helpers():
    assert tv._fmt_num(1.2345, 2) == "1.23"
    assert tv._fmt_vol(199_247_216) == "199.2M"
    assert tv._fmt_vol(95498) == "95K"


def test_stamp_tv_fields_on_entry():
    snap = tv.TvTaSnapshot(
        symbol="NVDA",
        recommendation="STRONG_BUY",
        bb_rating="NEAR_UPPER",
        bb_sigma=1.2,
        rsi=62.0,
    )
    row = tv.stamp_tv_fields_on_entry({"symbol": "NVDA", "action": "ENTER"}, snap)
    assert row["tv_recommendation"] == "STRONG_BUY"
    assert row["tv_bb_rating"] == "NEAR_UPPER"
    assert row["action"] == "ENTER"  # eligibility untouched


def test_post_tv_ta_discord_uses_channel(monkeypatch):
    calls = []

    class Cfg:
        bot_token = "tok"
        channel_id = "1539794451612958761"
        webhook_url = None

    monkeypatch.setattr(
        "trading_agent.discord.config.DiscordConfig.tv_ta_channel_from_env",
        classmethod(lambda cls: Cfg()),
    )

    def fake_post(content, config, username=None):
        calls.append({"content": content, "channel": config.channel_id, "user": username})
        return [{"ok": True}]

    monkeypatch.setattr("trading_agent.discord.poster.post_message", fake_post)
    out = tv.post_tv_ta_discord("# hello\n| a | b |", title="TV test")
    assert out.get("ok") is True
    assert out.get("channel_id") == "1539794451612958761"
    assert "TV test" in calls[0]["content"]
    assert "research only" in calls[0]["content"]


def test_bollinger_extreme_scan(monkeypatch):
    def fake_enrich(symbols, **kwargs):
        return {
            "enabled": True,
            "skipped": False,
            "symbols": [
                {"symbol": "A", "bb_sigma": 2.5, "bb_rating": "EXT_PLUS2"},
                {"symbol": "B", "bb_sigma": 0.2, "bb_rating": "INSIDE"},
                {"symbol": "C", "bb_sigma": -3.1, "bb_rating": "EXT_MINUS3"},
            ],
        }

    monkeypatch.setattr(tv, "enrich_symbols", fake_enrich)
    pack = tv.bollinger_extreme_scan(["A", "B", "C"], min_abs_sigma=2.0, force=True)
    assert pack["hit_count"] == 2
    syms = {h["symbol"] for h in pack["hits"]}
    assert syms == {"A", "C"}
