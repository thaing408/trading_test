"""Reddit public-JSON scorer + social blend (no network)."""

from __future__ import annotations

from trading_agent.firm.analysts import build_sentiment_report
from trading_agent.firm.reddit_sentiment import blend_social, score_posts


def test_score_posts_bullish_mentions():
    posts = [
        {"title": "$NVDA calls going to the moon", "selftext": "bullish breakout", "ups": 40, "subreddit": "wallstreetbets"},
        {"title": "NVDA squeeze setup", "selftext": "long", "ups": 20, "subreddit": "stocks"},
        {"title": "Unrelated AAPL dump", "selftext": "", "ups": 99, "subreddit": "stocks"},
        {"title": "NVDA looks overvalued short", "selftext": "puts", "ups": 5, "subreddit": "investing"},
    ]
    r = score_posts("NVDA", posts)
    assert r["status"] == "ok"
    assert r["n"] == 3
    assert r["bullish_n"] >= 2
    assert r["score"] > 0
    assert r["tilt"] == "bullish"


def test_short_ticker_requires_dollar():
    posts = [
        {"title": "I am going to the store", "selftext": "", "ups": 50, "subreddit": "stocks"},
        {"title": "$AI breakout", "selftext": "calls", "ups": 10, "subreddit": "wallstreetbets"},
    ]
    r = score_posts("AI", posts)
    assert r["n"] == 1
    assert r["status"] == "ok"


def test_blend_uses_reddit_when_n_ge_3():
    news = {
        "status": "ok",
        "symbol": "QQQ",
        "score": 10.0,
        "tilt": "neutral",
        "peaks": ["+beat"],
        "source": "news_tone_proxy",
    }
    reddit = {
        "status": "ok",
        "score": 80.0,
        "tilt": "bullish",
        "n": 5,
        "bullish_n": 4,
        "bearish_n": 1,
        "peaks": ["+r/wallstreetbets"],
        "top_posts": [{"title": "QQQ moon", "ups": 10}],
    }
    out = blend_social(news, reddit)
    assert out["source"] == "reddit+news_tone"
    assert out["score"] == round(0.4 * 10 + 0.6 * 80, 1)
    assert out["reddit"]["n"] == 5
    assert out["news_tone_score"] == 10.0


def test_blend_falls_back_when_reddit_thin():
    news = {
        "status": "ok",
        "symbol": "AAPL",
        "score": 20.0,
        "tilt": "bullish",
        "peaks": ["+surge"],
        "source": "news_tone_proxy",
    }
    reddit = {"status": "empty", "score": 0.0, "tilt": "neutral", "n": 0}
    out = blend_social(news, reddit)
    assert out["score"] == 20.0
    assert out["source"] == "news_tone_proxy"
    assert out["reddit"]["status"] == "empty"


def test_sentiment_report_carries_reddit_field():
    social = {
        "status": "ok",
        "score": 40.0,
        "tilt": "bullish",
        "peaks": ["+r/stocks"],
        "engagement_notes": "reddit n=4",
        "source": "reddit+news_tone",
        "news_tone_score": 10.0,
        "reddit": {"status": "ok", "n": 4, "tilt": "bullish", "score": 60.0},
    }
    r = build_sentiment_report("QQQ", "2026-08-21", social, use_llm=False)
    assert r.reddit.get("n") == 4
    assert r.news_tone_score == 10.0
    assert any("reddit" in s for s in r.sources)
    assert any("not auto-ENTER" in x for x in r.reasons)


def test_gather_social_uses_blend(monkeypatch):
    from trading_agent.firm import gather as g

    monkeypatch.setattr(
        g,
        "gather_news",
        lambda symbol, limit=12: {
            "status": "ok",
            "items": [{"headline": "QQQ surge to record"}],
        },
    )
    fake_reddit = {
        "status": "ok",
        "score": 50.0,
        "tilt": "bullish",
        "n": 4,
        "bullish_n": 3,
        "bearish_n": 1,
        "peaks": ["+r/stocks"],
        "top_posts": [],
        "source": "reddit_public_json",
    }
    monkeypatch.setattr(
        "trading_agent.firm.reddit_sentiment.fetch_reddit_sentiment",
        lambda symbol: fake_reddit,
    )
    out = g.gather_social("QQQ", news={"status": "ok", "items": [{"headline": "QQQ surge to record"}]})
    assert out["reddit"]["n"] == 4
    assert out["source"] == "reddit+news_tone"
