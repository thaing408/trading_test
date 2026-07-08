"""Liquid stock/ETF screener collector."""

from __future__ import annotations

from typing import List

from trading_agent.config import AgentConfig
from trading_agent.models import ScreenerCandidate, ScreenerResult

from .base import load_fixture, safe_fetch

SECTOR_MAP = {
    "AAPL": "Technology", "MSFT": "Technology", "NVDA": "Technology",
    "AMZN": "Consumer", "META": "Technology", "GOOGL": "Technology",
    "TSLA": "Consumer", "AMD": "Technology", "JPM": "Financials",
    "SPY": "Broad Market", "QQQ": "Technology", "IWM": "Small Cap",
    "XLE": "Energy", "XLF": "Financials", "GLD": "Commodities", "TLT": "Bonds",
}


def _screen_symbol(symbol: str, min_price: float, max_price: float) -> ScreenerCandidate | None:
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="1mo", interval="1d")
    if hist.empty or len(hist) < 5:
        return None
    price = float(hist["Close"].iloc[-1])
    if price < min_price or price > max_price:
        return None
    volume = int(hist["Volume"].iloc[-1])
    avg_vol = float(hist["Volume"].iloc[-21:].mean()) if len(hist) >= 21 else float(hist["Volume"].mean())
    rel_vol = volume / avg_vol if avg_vol else 1.0

    oi = 0
    spread_pct = 2.0
    liquidity = 50.0
    try:
        expirations = ticker.options
        if expirations:
            chain = ticker.option_chain(expirations[0])
            calls = chain.calls
            if not calls.empty:
                atm = calls.iloc[(calls["strike"] - price).abs().argsort()[:1]]
                oi = int(atm["openInterest"].iloc[0]) if "openInterest" in atm else 0
                bid = float(atm["bid"].iloc[0]) if "bid" in atm else 0
                ask = float(atm["ask"].iloc[0]) if "ask" in atm else 0
                mid = (bid + ask) / 2 if (bid + ask) else price * 0.01
                spread_pct = ((ask - bid) / mid * 100) if mid else 5.0
                liquidity = min(100.0, max(0.0, 100 - spread_pct * 5 + (oi / 50)))
    except Exception:
        pass

    return ScreenerCandidate(
        symbol=symbol,
        price=round(price, 2),
        volume=volume,
        relative_volume=round(rel_vol, 2),
        options_liquidity_score=round(liquidity, 1),
        open_interest=oi,
        bid_ask_spread_pct=round(spread_pct, 2),
        sector=SECTOR_MAP.get(symbol, "Unknown"),
    )


def _fixture_screener() -> ScreenerResult:
    data = load_fixture("screener_candidates.json")
    candidates = [ScreenerCandidate(**c) for c in data.get("candidates", [])]
    return ScreenerResult(source="fixture", candidates=candidates)


def collect_screener_candidates(config: AgentConfig) -> ScreenerResult:
    if config.fixture_mode or not config.use_live_data:
        return _fixture_screener()

    errors: List[str] = []
    candidates: List[ScreenerCandidate] = []
    for symbol in config.screener.symbols:
        result = safe_fetch(
            lambda s=symbol: _screen_symbol(s, config.screener.min_price, config.screener.max_price),
            None,
            errors,
        )
        if result:
            candidates.append(result)

    if not candidates:
        screener = _fixture_screener()
        screener.errors.extend(errors)
        screener.source = "fixture-fallback"
        return screener
    return ScreenerResult(source="yfinance", candidates=candidates, errors=errors)