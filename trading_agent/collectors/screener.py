"""Liquid stock/ETF screener collector — wide scan, soft floors, tight trade path later."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

from trading_agent.config import AgentConfig, ScreenerConfig
from trading_agent.models import ScreenerCandidate, ScreenerResult
from trading_agent.screener.universe import resolve_screener_symbols, sector_for

from .base import load_fixture, safe_fetch


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
    elif market_cap >= 1_000_000_000:
        score += 5.0
    if avg_daily_volume >= 2_000_000:
        score += 10.0
    elif avg_daily_volume >= 1_000_000:
        score += 5.0
    return round(min(100.0, score), 1)


def _passes_scan_floors(
    *,
    price: float,
    avg_vol: int,
    rel_vol: float,
    market_cap: float,
    oi: int,
    spread_pct: float,
    sc: ScreenerConfig,
) -> tuple[bool, str]:
    """Soft scan-tier floors (looser than RiskConfig trade path)."""
    scan_floor = float(sc.min_price)
    if getattr(sc, "allow_liquid_mid_price", False):
        scan_floor = min(
            scan_floor,
            float(getattr(sc, "liquid_mid_min_price", 5.0) or 5.0),
        )
    if price < scan_floor or price > sc.max_price:
        return False, f"price ${price:.2f} outside scan band"
    hard_adv = int(sc.min_avg_daily_volume * max(0.05, float(sc.hard_adv_fraction)))
    if avg_vol < hard_adv:
        return False, f"ADV {avg_vol} below hard floor {hard_adv}"
    if avg_vol < sc.min_avg_daily_volume:
        # Soft miss: still keep if above hard floor (watchlist coverage)
        pass
    if sc.hard_rvol_filter and rel_vol < sc.min_relative_volume:
        return False, f"RVOL {rel_vol:.2f}x below scan min {sc.min_relative_volume}"
    if market_cap > 0 and market_cap < sc.min_market_cap * 0.5:
        # Only hard-drop severe microcaps; unknown mcap kept
        return False, f"market cap ${market_cap:,.0f} far below scan floor"
    if oi > 0 and oi < sc.min_open_interest and spread_pct > sc.max_bid_ask_spread_pct:
        return False, "options chain too illiquid for scan"
    return True, ""


def _screen_symbol(symbol: str, config: AgentConfig) -> ScreenerCandidate | None:
    import yfinance as yf

    sc = config.screener
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="1mo", interval="1d")
    if hist.empty or len(hist) < 5:
        return None
    price = float(hist["Close"].iloc[-1])
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

    ok, _reason = _passes_scan_floors(
        price=price,
        avg_vol=avg_vol,
        rel_vol=rel_vol,
        market_cap=market_cap,
        oi=oi,
        spread_pct=spread_pct,
        sc=sc,
    )
    if not ok:
        return None

    inst = _institutional_score(rel_vol, oi, liquidity, market_cap, avg_vol)

    return ScreenerCandidate(
        symbol=symbol,
        price=round(price, 2),
        volume=volume,
        relative_volume=round(rel_vol, 2),
        options_liquidity_score=round(liquidity, 1),
        open_interest=oi,
        bid_ask_spread_pct=round(spread_pct, 2),
        sector=sector_for(symbol),
        avg_daily_volume=avg_vol,
        market_cap=market_cap,
        institutional_score=inst,
        options_volume=options_volume,
    )


def _fixture_screener() -> ScreenerResult:
    data = load_fixture("screener_candidates.json")
    candidates = [ScreenerCandidate(**c) for c in data.get("candidates", [])]
    return ScreenerResult(source="fixture", candidates=candidates)


def _resolve_symbol_list(config: AgentConfig) -> List[str]:
    symbols = resolve_screener_symbols(config.screener.symbols)
    cap = int(getattr(config.screener, "max_symbols", 0) or 0)
    if cap > 0:
        symbols = symbols[:cap]
    return symbols


def collect_screener_candidates(config: AgentConfig) -> ScreenerResult:
    if config.fixture_mode or not config.use_live_data:
        return _fixture_screener()

    errors: List[str] = []
    candidates: List[ScreenerCandidate] = []
    symbols = _resolve_symbol_list(config)
    workers = max(1, int(getattr(config.screener, "fetch_workers", 6) or 1))

    def _one(sym: str) -> Optional[ScreenerCandidate]:
        return safe_fetch(
            lambda s=sym: _screen_symbol(s, config),
            None,
            errors,
        )

    if workers == 1 or len(symbols) <= 4:
        for symbol in symbols:
            result = _one(symbol)
            if result:
                candidates.append(result)
    else:
        with ThreadPoolExecutor(max_workers=min(workers, len(symbols))) as pool:
            futs = {pool.submit(_one, sym): sym for sym in symbols}
            for fut in as_completed(futs):
                try:
                    result = fut.result()
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{futs[fut]}: {exc}")
                    continue
                if result:
                    candidates.append(result)

    # Stable order: higher RVOL / institutional first for downstream watchlist bias
    candidates.sort(
        key=lambda c: (c.relative_volume, c.institutional_score or 0.0, c.volume),
        reverse=True,
    )

    if not candidates:
        return ScreenerResult(
            source="unavailable",
            candidates=[],
            errors=errors
            or [
                f"No live screener candidates from {len(symbols)} symbols; "
                "not injecting fixture"
            ],
        )
    return ScreenerResult(
        source="yfinance",
        candidates=candidates,
        errors=errors
        + [
            f"scan_universe={len(symbols)} returned={len(candidates)} "
            f"workers={workers}"
        ],
    )
