"""Load historical OHLCV for offline research (G3.1).

Uses existing ``market_data.get_ohlcv`` (Schwab auto → yfinance). Falls back to
synthetic multi-regime data when network/providers fail (tests / offline CI).
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Sequence

from trading_agent.backtest.data import default_backtest_universe

logger = logging.getLogger(__name__)

DEFAULT_HIST_SYMBOLS = [
    "SPY",
    "QQQ",
    "IWM",
    "AAPL",
    "MSFT",
    "NVDA",
    "AMD",
    "META",
    "AMZN",
    "TSLA",
    "JPM",
]


def load_historical_ohlcv(
    symbols: Optional[Sequence[str]] = None,
    *,
    period: str = "1y",
    interval: str = "1d",
    min_bars: int = 60,
    allow_synthetic_fallback: bool = True,
) -> Dict[str, dict]:
    """Fetch daily (or other) bars for symbols; align to common length.

    Returns symbol -> {close, high, low, volume, open?, source}.
    """
    from trading_agent.market_data.provider import get_ohlcv, last_ohlcv_source

    syms = [s.upper() for s in (symbols or DEFAULT_HIST_SYMBOLS)]
    raw: Dict[str, dict] = {}
    for sym in syms:
        try:
            bars = get_ohlcv(sym, config=None, interval=interval, period=period)
        except Exception as exc:  # network / provider
            logger.warning("historical OHLCV failed for %s: %s", sym, exc)
            bars = {"close": [], "high": [], "low": [], "volume": []}
        closes = list(bars.get("close") or [])
        if len(closes) < min_bars:
            logger.info("skip %s: only %d bars (need %d)", sym, len(closes), min_bars)
            continue
        pack = {
            "close": closes,
            "high": list(bars.get("high") or closes),
            "low": list(bars.get("low") or closes),
            "volume": list(bars.get("volume") or [1_000_000] * len(closes)),
            "source": last_ohlcv_source(sym),
        }
        if bars.get("open"):
            pack["open"] = list(bars["open"])
        # lightweight IV placeholders for options metrics path
        pack.setdefault("iv", 25.0)
        pack.setdefault("iv_history", [20, 22, 25, 28, 30, 26, 24, 27, 29, 25])
        raw[sym] = pack

    if not raw:
        if not allow_synthetic_fallback:
            return {}
        logger.warning("No historical bars — using synthetic multi-regime universe")
        synth = default_backtest_universe()
        for s in synth:
            synth[s]["source"] = "synthetic_fallback"
        return synth

    return align_ohlcv(raw)


def align_ohlcv(data: Dict[str, dict]) -> Dict[str, dict]:
    """Trim all series to the minimum common length (most recent bars)."""
    if not data:
        return {}
    n = min(len(v.get("close") or []) for v in data.values())
    if n <= 0:
        return {}
    out: Dict[str, dict] = {}
    for sym, pack in data.items():
        closes = list(pack.get("close") or [])[-n:]
        trimmed = {
            "close": closes,
            "high": list(pack.get("high") or closes)[-n:],
            "low": list(pack.get("low") or closes)[-n:],
            "volume": list(pack.get("volume") or [1_000_000] * n)[-n:],
            "source": pack.get("source", "unknown"),
        }
        if pack.get("open"):
            trimmed["open"] = list(pack["open"])[-n:]
        if "iv" in pack:
            trimmed["iv"] = pack["iv"]
        if "iv_history" in pack:
            trimmed["iv_history"] = pack["iv_history"]
        out[sym] = trimmed
    return out


def ohlcv_provenance(data: Dict[str, dict]) -> Dict[str, str]:
    return {sym: str(pack.get("source") or "unknown") for sym, pack in data.items()}
