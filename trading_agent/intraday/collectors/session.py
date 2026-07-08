"""Collect intraday session monitoring data."""

from __future__ import annotations

from typing import Dict, List

from trading_agent.collectors.base import load_fixture, safe_fetch
from trading_agent.intraday.config import IntradayConfig
from trading_agent.intraday.models import OpenPosition, SessionSnapshot, SymbolSessionData

SECTOR_ETFS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU"]


def _fixture_snapshot(symbols: List[str]) -> SessionSnapshot:
    data = load_fixture("intraday_session.json")
    sym_data = {}
    for sym in symbols:
        if sym in data.get("symbols", {}):
            sym_data[sym] = SymbolSessionData(symbol=sym, **data["symbols"][sym])
    return SessionSnapshot(
        source="fixture",
        market_regime=data.get("market_regime", "neutral"),
        prior_regime=data.get("prior_regime", "neutral"),
        vix=data.get("vix", 18.0),
        vix_change_pct=data.get("vix_change_pct", 0.0),
        breadth_advancers=data.get("breadth_advancers", 0),
        breadth_decliners=data.get("breadth_decliners", 0),
        breadth_ratio=data.get("breadth_ratio", 1.0),
        sector_leaders=data.get("sector_leaders", []),
        sector_laggards=data.get("sector_laggards", []),
        symbols=sym_data,
        breaking_news=data.get("breaking_news", []),
        economic_announcements=data.get("economic_announcements", []),
    )


def _fetch_symbol_session(symbol: str) -> SymbolSessionData:
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="1d", interval="5m")
    if hist.empty:
        raise ValueError(f"No intraday data for {symbol}")
    closes = hist["Close"].tolist()
    highs = hist["High"].tolist()
    lows = hist["Low"].tolist()
    volumes = hist["Volume"].tolist()
    price = float(closes[-1])
    prev = float(closes[0]) if closes else price
    change_pct = ((price - prev) / prev * 100) if prev else 0.0
    vwap = sum(c * v for c, v in zip(closes, volumes)) / sum(volumes) if sum(volumes) else price
    rel_vol = float(volumes[-1]) / (sum(volumes[:-1]) / max(len(volumes) - 1, 1)) if len(volumes) > 1 else 1.0
    support = float(min(lows[-12:])) if lows else price * 0.98
    resistance = float(max(highs[-12:])) if highs else price * 1.02
    slope = (closes[-1] - closes[max(0, len(closes) - 6)]) / closes[max(0, len(closes) - 6)] if len(closes) > 1 else 0
    trend = "uptrend" if slope > 0.005 else "downtrend" if slope < -0.005 else "sideways"
    momentum = "accelerating" if slope > 0.01 else "decelerating" if slope < -0.01 else "steady"

    iv, oi, delta = 25.0, 0, 0.5
    try:
        if ticker.options:
            chain = ticker.option_chain(ticker.options[0])
            calls = chain.calls
            if not calls.empty:
                atm = calls.iloc[(calls["strike"] - price).abs().argsort()[:1]]
                iv = float(atm["impliedVolatility"].iloc[0]) * 100 if "impliedVolatility" in atm else 25.0
                oi = int(atm["openInterest"].iloc[0]) if "openInterest" in atm else 0
    except Exception:
        pass

    return SymbolSessionData(
        symbol=symbol,
        price=round(price, 2),
        change_pct=round(change_pct, 2),
        vwap=round(vwap, 2),
        volume=int(volumes[-1]) if volumes else 0,
        relative_volume=round(rel_vol, 2),
        support=round(support, 2),
        resistance=round(resistance, 2),
        trend=trend,
        momentum=momentum,
        iv=round(iv, 2),
        iv_change_pct=0.0,
        open_interest=oi,
        oi_change_pct=0.0,
        delta=round(delta, 4),
        gamma=0.01,
        theta=-0.05,
        vega=0.1,
        options_flow_bias="bullish" if trend == "uptrend" else "bearish" if trend == "downtrend" else "neutral",
    )


def _fetch_breadth_and_sectors(errors: List[str]) -> dict:
    import yfinance as yf

    result = {"advancers": 0, "decliners": 0, "leaders": [], "laggards": []}
    changes = []
    for etf in SECTOR_ETFS:
        data = safe_fetch(
            lambda e=etf: _etf_change(yf.Ticker(e)),
            None,
            errors,
        )
        if data is not None:
            changes.append((etf, data))
            if data > 0:
                result["advancers"] += 1
            elif data < 0:
                result["decliners"] += 1
    if changes:
        changes.sort(key=lambda x: x[1], reverse=True)
        result["leaders"] = [c[0] for c in changes[:3]]
        result["laggards"] = [c[0] for c in changes[-3:]]
    total = result["advancers"] + result["decliners"]
    result["ratio"] = result["advancers"] / total if total else 1.0
    return result


def _etf_change(ticker) -> float:
    hist = ticker.history(period="1d", interval="5m")
    if hist.empty or len(hist) < 2:
        return 0.0
    return float((hist["Close"].iloc[-1] - hist["Close"].iloc[0]) / hist["Close"].iloc[0] * 100)


def collect_session_snapshot(
    config: IntradayConfig,
    positions: List[OpenPosition],
    plan_context: dict,
) -> SessionSnapshot:
    symbols = list({p.symbol for p in positions} | set(config.watch_symbols))
    if config.fixture_mode or not config.use_live_data:
        return _fixture_snapshot(symbols)

    errors: List[str] = []
    sym_data: Dict[str, SymbolSessionData] = {}
    for sym in symbols:
        data = safe_fetch(lambda s=sym: _fetch_symbol_session(s), None, errors)
        if data:
            sym_data[sym] = data

    breadth = _fetch_breadth_and_sectors(errors)
    vix_data = safe_fetch(
        lambda: _etf_change(__import__("yfinance").Ticker("^VIX")),
        0.0,
        errors,
    )

    regime = plan_context.get("market_regime", "neutral")
    news_items = plan_context.get("news_highlights", [])

    if not sym_data:
        snap = _fixture_snapshot(symbols)
        snap.errors.extend(errors)
        snap.source = "fixture-fallback"
        return snap

    return SessionSnapshot(
        source="yfinance",
        market_regime=_infer_regime(breadth.get("ratio", 1.0), vix_data),
        prior_regime=regime,
        vix=18.0,
        vix_change_pct=round(vix_data, 2),
        breadth_advancers=breadth.get("advancers", 0),
        breadth_decliners=breadth.get("decliners", 0),
        breadth_ratio=breadth.get("ratio", 1.0),
        sector_leaders=breadth.get("leaders", []),
        sector_laggards=breadth.get("laggards", []),
        symbols=sym_data,
        breaking_news=news_items[:5],
        economic_announcements=plan_context.get("high_impact_events", []),
        errors=errors,
    )


def _infer_regime(breadth_ratio: float, vix_chg: float) -> str:
    if breadth_ratio > 0.6 and vix_chg < 2:
        return "bullish"
    if breadth_ratio < 0.4 or vix_chg > 5:
        return "bearish"
    return "neutral"