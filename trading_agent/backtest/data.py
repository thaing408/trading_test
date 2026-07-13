"""Multi-regime synthetic OHLCV for offline backtests (deterministic, no network).

Builds bull / chop / bear segments so directional stops, iron-condor breaks, and
grade filters can actually diverge — pure fixture uptrends made every trade win.
"""

from __future__ import annotations

from typing import Dict, List
from zlib import adler32

from trading_agent.collectors.base import load_fixture


def _stable_sym_seed(symbol: str) -> int:
    return adler32(symbol.encode("utf-8")) & 0xFFFFFFFF


def _segment(
    start: float,
    n: int,
    *,
    drift: float,
    vol: float,
    seed: int,
) -> tuple[List[float], List[float], List[float], List[float]]:
    """Generate n daily bars with deterministic pseudo-noise from seed."""
    closes: List[float] = []
    highs: List[float] = []
    lows: List[float] = []
    vols: List[float] = []
    px = start
    for i in range(n):
        # LCG-ish noise in [-1, 1]
        noise = (((seed * 1103515245 + i * 12345) % 1000) / 500.0) - 1.0
        ret = drift + vol * noise
        open_px = px
        px = max(1.0, px * (1.0 + ret))
        # Intrabar range scales with vol
        rng = abs(px) * (vol * 1.8 + 0.002)
        # Occasional shock bar for stop tests
        if (seed + i) % 17 == 0:
            rng *= 2.5
            if noise < 0:
                px = max(1.0, px * (1.0 - vol * 2))
            else:
                px = px * (1.0 + vol * 2)
        hi = max(open_px, px) + rng * 0.5
        lo = min(open_px, px) - rng * 0.5
        closes.append(round(px, 4))
        highs.append(round(hi, 4))
        lows.append(round(max(0.5, lo), 4))
        vols.append(float(2_000_000 + abs(int(noise * 1_000_000))))
    return closes, highs, lows, vols


def build_multiregime_ohlcv(
    *,
    bars_per_regime: int = 25,
    symbols: List[str] | None = None,
) -> Dict[str, dict]:
    """Return symbol -> {close, high, low, volume} with bull→chop→bear→bull path."""
    base = load_fixture("ohlcv.json")
    syms = symbols or [
        "NVDA", "AMD", "AAPL", "MSFT", "SPY", "QQQ", "TSLA", "META", "AMZN", "JPM",
    ]
    # Symbol-specific seeds and beta to market
    meta = {
        "NVDA": (11, 1.4, 100.0),
        "AMD": (22, 1.3, 90.0),
        "AAPL": (33, 0.9, 180.0),
        "MSFT": (44, 0.85, 350.0),
        "SPY": (55, 1.0, 450.0),
        "QQQ": (66, 1.15, 380.0),
        "TSLA": (77, 1.6, 200.0),
        "META": (88, 1.2, 400.0),
        "AMZN": (99, 1.1, 160.0),
        "JPM": (13, 0.8, 150.0),
    }
    # Regimes: (drift_per_bar, vol)
    regimes = [
        (0.004, 0.008),   # bull
        (0.0005, 0.012),  # chop / elevated vol
        (-0.005, 0.015),  # bear
        (0.003, 0.009),   # recovery bull
    ]
    out: Dict[str, dict] = {}
    for sym in syms:
        seed, beta, start = meta.get(sym, (_stable_sym_seed(sym) % 97, 1.0, 100.0))
        # Prefer fixture last price as start if present
        if sym in base and base[sym].get("close"):
            start = float(base[sym]["close"][0])
        c_all: List[float] = []
        h_all: List[float] = []
        l_all: List[float] = []
        v_all: List[float] = []
        px0 = start
        for ri, (drift, vol) in enumerate(regimes):
            c, h, l, v = _segment(
                px0,
                bars_per_regime,
                drift=drift * beta,
                vol=vol * (0.8 + 0.4 * (beta - 0.5)),
                seed=seed + ri * 1000,
            )
            c_all.extend(c)
            h_all.extend(h)
            l_all.extend(l)
            v_all.extend(v)
            px0 = c[-1]
        # Attach simple iv history seed for options
        out[sym] = {
            "close": c_all,
            "high": h_all,
            "low": l_all,
            "volume": v_all,
            "iv": 28.0 + (seed % 10),
            "iv_history": [20, 22, 25, 30, 35, 28, 24, 40, 32, 26],
        }
    return out


def default_backtest_universe() -> Dict[str, dict]:
    return build_multiregime_ohlcv()
