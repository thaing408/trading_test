"""Live data gathers for firm tools (P1) — fail closed to empty dicts."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def gather_ohlcv(symbol: str, *, period: str = "6mo", interval: str = "1d") -> Dict[str, Any]:
    try:
        from trading_agent.market_data.provider import get_ohlcv

        bars = get_ohlcv(symbol, interval=interval, period=period) or {}
        closes = list(bars.get("Close") or bars.get("close") or [])
        highs = list(bars.get("High") or bars.get("high") or [])
        lows = list(bars.get("Low") or bars.get("low") or [])
        opens = list(bars.get("Open") or bars.get("open") or [])
        vols = list(bars.get("Volume") or bars.get("volume") or [])
        n = min(len(closes), len(highs), len(lows))
        if n < 5:
            return {"status": "empty", "symbol": symbol, "n": n}
        return {
            "status": "ok",
            "symbol": symbol.upper(),
            "n": n,
            "last": float(closes[-1]),
            "prev": float(closes[-2]) if n >= 2 else float(closes[-1]),
            "change_pct": round((float(closes[-1]) / float(closes[-2]) - 1) * 100, 2)
            if n >= 2 and float(closes[-2])
            else 0.0,
            "closes": [float(x) for x in closes[-120:]],
            "highs": [float(x) for x in highs[-120:]],
            "lows": [float(x) for x in lows[-120:]],
            "opens": [float(x) for x in opens[-120:]] if opens else [],
            "volumes": [float(x) for x in vols[-120:]] if vols else [],
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "symbol": symbol, "error": str(exc)}


def gather_ta_bundle(symbol: str, ohlcv: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = ohlcv if ohlcv and ohlcv.get("status") == "ok" else gather_ohlcv(symbol)
    if data.get("status") != "ok":
        return {"status": data.get("status", "empty"), "symbol": symbol, "error": data.get("error")}
    try:
        from trading_agent.analysis import technical as ta

        closes = data["closes"]
        highs = data["highs"]
        lows = data["lows"]
        vols = data.get("volumes") or []
        bundle = {
            "status": "ok",
            "symbol": symbol.upper(),
            "last": data["last"],
            "change_pct": data.get("change_pct"),
            "rsi14": round(ta.rsi(closes, 14), 2),
            "macd": ta.macd_signal(closes),
            "ma_alignment": ta.ma_alignment(closes),
            "bollinger": ta.bollinger_position(closes, 20),
            "atr14": ta.atr(highs, lows, closes, 14),
            "adx14": ta.adx(highs, lows, closes, 14),
            "support_resistance": list(ta.support_resistance(lows, highs)),
            "vwap_relation": ta.vwap_relation(closes, vols) if vols else "n/a",
        }
        # soft regime label
        rsi = bundle["rsi14"]
        align = bundle["ma_alignment"]
        if align == "bullish" and rsi < 75:
            bundle["regime"] = "uptrend"
            bundle["bias"] = "bullish"
        elif align == "bearish" and rsi > 25:
            bundle["regime"] = "downtrend"
            bundle["bias"] = "bearish"
        else:
            bundle["regime"] = "range_or_mixed"
            bundle["bias"] = "neutral"
        return bundle
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "symbol": symbol, "error": str(exc)}


def gather_news(symbol: str, *, limit: int = 12) -> Dict[str, Any]:
    try:
        from trading_agent.collectors.news import collect_news_catalysts, headline_mentions_symbol
        from trading_agent.config import AgentConfig

        cfg = AgentConfig()
        # Prefer network; fixture_mode false
        try:
            cfg.fixture_mode = False
        except Exception:
            pass
        cat = collect_news_catalysts(cfg, [symbol.upper()])
        items = []
        for it in getattr(cat, "items", None) or []:
            headline = str(getattr(it, "headline", None) or getattr(it, "title", "") or "")
            if not headline:
                continue
            if not headline_mentions_symbol(symbol, headline) and symbol.upper() not in headline.upper():
                # keep a few general macro if category geopolitical
                cat_name = str(getattr(it, "category", "") or "")
                if cat_name not in ("geopolitical", "macro", "general"):
                    continue
            items.append(
                {
                    "headline": headline[:200],
                    "category": str(getattr(it, "category", "") or "general"),
                    "source": str(getattr(it, "source", "") or cat.source),
                }
            )
            if len(items) >= limit:
                break
        return {
            "status": "ok" if items else "empty",
            "symbol": symbol.upper(),
            "source": getattr(cat, "source", ""),
            "items": items,
            "errors": list(getattr(cat, "errors", None) or [])[:5],
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "symbol": symbol, "error": str(exc), "items": []}


def gather_fundamentals(symbol: str) -> Dict[str, Any]:
    try:
        from trading_agent.fundamentals.quality import fetch_fundamental_snapshot

        snap = fetch_fundamental_snapshot(symbol, use_network=True)
        d = snap.as_dict()
        d["status"] = "ok" if snap.source not in ("none", "offline") or snap.score else "empty"
        return d
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "symbol": symbol, "error": str(exc), "score": 0.0}


def gather_insider(symbol: str, news: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Proxy: filter news for insider-category headlines (no Form-4 feed yet)."""
    news = news if news is not None else gather_news(symbol)
    items = [
        it
        for it in (news.get("items") or [])
        if str(it.get("category") or "").lower() in ("insider", "sec_filing")
    ]
    return {
        "status": "ok" if items else "empty",
        "symbol": symbol.upper(),
        "items": items[:8],
        "note": "P1 proxy via news categories — structured Form-4 later",
    }


_POS = (
    "beat",
    "surge",
    "rally",
    "upgrade",
    "record",
    "growth",
    "bullish",
    "soar",
    "jump",
    "wins",
    "approval",
)
_NEG = (
    "miss",
    "fall",
    "drop",
    "downgrade",
    "probe",
    "lawsuit",
    "cut",
    "bearish",
    "plunge",
    "recall",
    "fraud",
    "delay",
)


def gather_social(symbol: str, news: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """News-tone proxy until X/Reddit feeds exist."""
    news = news if news is not None else gather_news(symbol)
    items = news.get("items") or []
    score = 0
    peaks: List[str] = []
    for it in items:
        h = str(it.get("headline") or "").lower()
        for w in _POS:
            if w in h:
                score += 1
                peaks.append(f"+{w}")
        for w in _NEG:
            if w in h:
                score -= 1
                peaks.append(f"-{w}")
    # map to -100..100 soft
    n = max(len(items), 1)
    tilted = max(-100.0, min(100.0, (score / n) * 40.0))
    if tilted > 15:
        tilt = "bullish"
    elif tilted < -15:
        tilt = "bearish"
    else:
        tilt = "neutral"
    return {
        "status": "ok" if items else "empty",
        "symbol": symbol.upper(),
        "score": round(tilted, 1),
        "tilt": tilt,
        "peaks": peaks[:12],
        "engagement_notes": f"news_tone_proxy n={len(items)} (no X/Reddit yet)",
        "source": "news_tone_proxy",
    }
