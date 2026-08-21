"""Public Reddit JSON sentiment (research-only; never feeds OMS).

Uses Reddit's unauthenticated search JSON. Fail-closed on timeout/block.
Does not use Marketaux or the TradingView MCP process — Grok talks to that
MCP separately. This path keeps firm/desk cards working without MCP.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

_SUBS = (
    "wallstreetbets",
    "stocks",
    "options",
    "investing",
    "StockMarket",
    "daytrading",
    "pennystocks",
)
_POS = (
    "bull",
    "bullish",
    "calls",
    "moon",
    "squeeze",
    "breakout",
    "long",
    "buy",
    "tendies",
    "rocket",
    "undervalued",
    "accumulate",
)
_NEG = (
    "bear",
    "bearish",
    "puts",
    "crash",
    "dump",
    "short",
    "overvalued",
    "baghold",
    "drill",
    "rip",
    "avoid",
    "sell",
)


def reddit_enabled() -> bool:
    raw = os.getenv("TRADING_AGENT_REDDIT", "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _timeout() -> float:
    try:
        return max(2.0, float(os.getenv("TRADING_AGENT_REDDIT_TIMEOUT", "8") or 8))
    except ValueError:
        return 8.0


def _tilt(score: float) -> str:
    if score > 15:
        return "bullish"
    if score < -15:
        return "bearish"
    return "neutral"


def _mentions(symbol: str, text: str) -> bool:
    t = (text or "").upper()
    sym = symbol.upper()
    if f"${sym}" in t:
        return True
    if len(sym) <= 2:
        return False
    return re.search(rf"\b{re.escape(sym)}\b", t) is not None


def _post_sign(title: str, body: str) -> int:
    blob = f"{title} {body}".lower()
    pos = sum(1 for w in _POS if w in blob)
    neg = sum(1 for w in _NEG if w in blob)
    if pos > neg:
        return 1
    if neg > pos:
        return -1
    return 0


def score_posts(symbol: str, posts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Pure scorer for tests — posts are Reddit listing children.data dicts."""
    matched: List[Dict[str, Any]] = []
    signed_ups = 0.0
    total_ups = 0.0
    peaks: List[str] = []
    for p in posts:
        title = str(p.get("title") or "")
        body = str(p.get("selftext") or "")
        if not _mentions(symbol, f"{title} {body}"):
            continue
        ups = float(p.get("ups") or p.get("score") or 0)
        if ups < 0:
            ups = 0.0
        sign = _post_sign(title, body)
        signed_ups += sign * (ups + 1.0)
        total_ups += ups + 1.0
        sub = str(p.get("subreddit") or "")
        matched.append(
            {
                "title": title[:160],
                "subreddit": sub,
                "ups": int(ups),
                "sign": sign,
            }
        )
        if sign > 0:
            peaks.append(f"+r/{sub}")
        elif sign < 0:
            peaks.append(f"-r/{sub}")
        if len(matched) >= 25:
            break

    n = len(matched)
    if n == 0 or total_ups <= 0:
        return {
            "status": "empty",
            "symbol": symbol.upper(),
            "score": 0.0,
            "tilt": "neutral",
            "n": 0,
            "bullish_n": 0,
            "bearish_n": 0,
            "peaks": [],
            "top_posts": [],
            "source": "reddit_public_json",
        }

    raw = (signed_ups / total_ups) * 100.0
    score = max(-100.0, min(100.0, raw))
    bull_n = sum(1 for m in matched if m["sign"] > 0)
    bear_n = sum(1 for m in matched if m["sign"] < 0)
    return {
        "status": "ok",
        "symbol": symbol.upper(),
        "score": round(score, 1),
        "tilt": _tilt(score),
        "n": n,
        "bullish_n": bull_n,
        "bearish_n": bear_n,
        "peaks": peaks[:12],
        "top_posts": matched[:8],
        "source": "reddit_public_json",
    }


def _fetch_listing(symbol: str) -> List[Dict[str, Any]]:
    import requests

    subs = "+".join(_SUBS)
    url = f"https://www.reddit.com/r/{subs}/search.json"
    headers = {
        "User-Agent": "trading-agent/0.1 research (by u/local-desk)",
        "Accept": "application/json",
    }
    params = {
        "q": f'"{symbol}" OR ${symbol}',
        "restrict_sr": "on",
        "sort": "new",
        "t": "day",
        "limit": "25",
        "type": "link",
    }
    r = requests.get(url, headers=headers, params=params, timeout=_timeout())
    r.raise_for_status()
    data = r.json()
    children = ((data.get("data") or {}).get("children")) or []
    out: List[Dict[str, Any]] = []
    for ch in children:
        d = ch.get("data") if isinstance(ch, dict) else None
        if isinstance(d, dict):
            out.append(d)
    return out


def fetch_reddit_sentiment(symbol: str) -> Dict[str, Any]:
    """Live fetch. Empty dict-shaped result on disable/error (fail closed)."""
    sym = (symbol or "").upper().strip()
    if not sym or not reddit_enabled():
        return {
            "status": "disabled",
            "symbol": sym,
            "score": 0.0,
            "tilt": "neutral",
            "n": 0,
            "bullish_n": 0,
            "bearish_n": 0,
            "peaks": [],
            "top_posts": [],
            "source": "reddit_public_json",
        }
    try:
        posts = _fetch_listing(sym)
        return score_posts(sym, posts)
    except Exception as exc:
        return {
            "status": "error",
            "symbol": sym,
            "score": 0.0,
            "tilt": "neutral",
            "n": 0,
            "bullish_n": 0,
            "bearish_n": 0,
            "peaks": [],
            "top_posts": [],
            "error": f"{type(exc).__name__}: {exc}"[:200],
            "source": "reddit_public_json",
        }


def blend_social(
    news_tone: Dict[str, Any],
    reddit: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """News-tone remains the fallback; Reddit is extra + blended when n>=3."""
    news_score = float(news_tone.get("score") or 0.0)
    news_tilt = str(news_tone.get("tilt") or "neutral")
    peaks = list(news_tone.get("peaks") or [])
    reddit = reddit if isinstance(reddit, dict) else {}
    r_status = str(reddit.get("status") or "")
    r_n = int(reddit.get("n") or 0)
    r_score = float(reddit.get("score") or 0.0)

    if r_status == "ok" and r_n >= 3:
        blended = 0.4 * news_score + 0.6 * r_score
        source = "reddit+news_tone"
        notes = (
            f"reddit n={r_n} score={r_score} tilt={reddit.get('tilt')} "
            f"(bull={reddit.get('bullish_n')} bear={reddit.get('bearish_n')}); "
            f"news_tone={news_score}"
        )
        peaks = list(reddit.get("peaks") or []) + peaks
        tilt = _tilt(blended)
        status = "ok"
    else:
        blended = news_score
        source = str(news_tone.get("source") or "news_tone_proxy")
        why = r_status or "absent"
        notes = f"news_tone_proxy n_news score={news_score}; reddit={why} n={r_n}"
        tilt = news_tilt
        status = str(news_tone.get("status") or "empty")
        if status not in ("ok", "empty"):
            status = "ok" if news_tone.get("peaks") else "empty"

    return {
        "status": status,
        "symbol": str(news_tone.get("symbol") or reddit.get("symbol") or ""),
        "score": round(float(blended), 1),
        "tilt": tilt,
        "peaks": peaks[:12],
        "engagement_notes": notes,
        "source": source,
        "news_tone_score": round(news_score, 1),
        "reddit": {
            "status": r_status or "absent",
            "score": round(r_score, 1),
            "tilt": str(reddit.get("tilt") or "neutral"),
            "n": r_n,
            "bullish_n": int(reddit.get("bullish_n") or 0),
            "bearish_n": int(reddit.get("bearish_n") or 0),
            "top_posts": list(reddit.get("top_posts") or [])[:8],
            "error": str(reddit.get("error") or ""),
        },
    }
