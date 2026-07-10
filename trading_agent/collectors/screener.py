"""Liquid stock/ETF screener collector with institutional floors."""

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
    "DIA": "Broad Market", "XLK": "Technology", "SMH": "Technology",
    "SOXX": "Technology", "XBI": "Healthcare",
    "XLE": "Energy", "XLF": "Financials", "GLD": "Commodities", "TLT": "Bonds",
}


def _institutional_score(
    relative_volume: float,
    open_interest: int,
    options_liquidity: float,
    market_cap: float,
    avg_daily_volume: int,
) -> float:
    """Proxy for institutional participation (0-100)."""
    score = 0.0
    score += min(30.0, relative_volume * 10.0)  # RVOL contribution
    score += min(25.0, open_interest / 400.0)
    score += min(25.0, options_liquidity * 0.25)
    if market_cap >= 2_000_000_000:
        score += 10.0
    if avg_daily_volume >= 2_000_000:
        score += 10.0
    return round(min(100.0, score), 1)


def _screen_symbol(symbol: str, config: AgentConfig) -> ScreenerCandidate | None:
    import yfinance as yf

    sc = config.screener
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="1mo", interval="1d")
    if hist.empty or len(hist) < 5:
        return None
    price = float(hist["Close"].iloc[-1])
    if price < sc.min_price or price > sc.max_price:
        return None
    volume = int(hist["Volume"].iloc[-1])
    avg_vol = int(
        float(hist["Volume"].iloc[-21:].mean())
        if len(hist) >= 21
        else float(hist["Volume"].mean())
    )
    rel_vol = volume / avg_vol if avg_vol else 1.0

    market_cap = 0.0
    try:
        info = ticker.fast_info
        market_cap = float(getattr(info, "market_cap", 0) or 0)
    except Exception:
        try:
            info = ticker.info or {}
            market_cap = float(info.get("marketCap") or 0)
        except Exception:
            market_cap = 0.0

    oi = 0
    options_volume = 0
    spread_pct = 5.0
    liquidity = 30.0
    try:
        expirations = ticker.options
        if expirations:
            chain = ticker.option_chain(expirations[0])
            calls = chain.calls
            if not calls.empty:
                atm = calls.iloc[(calls["strike"] - price).abs().argsort()[:1]]
                oi = int(atm["openInterest"].iloc[0]) if "openInterest" in atm else 0
                if "volume" in atm:
                    options_volume = int(atm["volume"].iloc[0] or 0)
                bid = float(atm["bid"].iloc[0]) if "bid" in atm else 0
                ask = float(atm["ask"].iloc[0]) if "ask" in atm else 0
                mid = (bid + ask) / 2 if (bid + ask) else price * 0.01
                spread_pct = ((ask - bid) / mid * 100) if mid else 5.0
                liquidity = min(100.0, max(0.0, 100 - spread_pct * 5 + (oi / 50)))
    except Exception:
        pass

    inst = _institutional_score(rel_vol, oi, liquidity, market_cap, avg_vol)

    # Soft pre-filter at collector: drop obvious non-liquid names early
    if avg_vol < sc.min_avg_daily_volume * 0.25:
        return None

    return ScreenerCandidate(
        symbol=symbol,
        price=round(price, 2),
        volume=volume,
        relative_volume=round(rel_vol, 2),
        options_liquidity_score=round(liquidity, 1),
        open_interest=oi,
        bid_ask_spread_pct=round(spread_pct, 2),
        sector=SECTOR_MAP.get(symbol, "Unknown"),
        avg_daily_volume=avg_vol,
        market_cap=market_cap,
        institutional_score=inst,
        options_volume=options_volume,
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
            lambda s=symbol: _screen_symbol(s, config),
            None,
            errors,
        )
        if result:
            candidates.append(result)

    if not candidates:
        return ScreenerResult(
            source="unavailable",
            candidates=[],
            errors=errors or ["No live screener candidates; not injecting fixture"],
        )
    return ScreenerResult(source="yfinance", candidates=candidates, errors=errors)
