"""Higher-timeframe PA bias (direction TF) for filtering LTF entries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from trading_agent.pa.structure import analyze_structure


@dataclass
class HtfBias:
    direction: str  # up | down | range | unknown
    strength: float  # 0–100
    source: str = ""
    notes: List[str] = field(default_factory=list)


def compute_htf_bias_from_ohlc(
    highs,
    lows,
    closes,
    *,
    source: str = "bars",
) -> HtfBias:
    st = analyze_structure(highs, lows, closes)
    strength = 50.0
    if st.trend == "up":
        strength = 70.0
        if st.last_bos == "bullish":
            strength += 10
    elif st.trend == "down":
        strength = 70.0
        if st.last_bos == "bearish":
            strength += 10
    elif st.trend == "range":
        strength = 45.0
    return HtfBias(
        direction=st.trend if st.trend != "unknown" else "range",
        strength=min(100.0, strength),
        source=source,
        notes=list(st.notes),
    )


def compute_htf_bias(
    symbol: str,
    *,
    period: str = "6mo",
    interval: str = "1d",
    source: str = "yfinance",
) -> HtfBias:
    """Fetch HTF bars and compute structure bias (daily default)."""
    try:
        from trading_agent.odte.multidte import fetch_htf_bars

        df = fetch_htf_bars(symbol, period=period, interval=interval, source=source)
        if df is None or len(df) < 10:
            return HtfBias(direction="unknown", strength=0.0, source="empty", notes=["no bars"])
        return compute_htf_bias_from_ohlc(
            df["High"].astype(float).tolist(),
            df["Low"].astype(float).tolist(),
            df["Close"].astype(float).tolist(),
            source=f"{interval}:{period}",
        )
    except Exception as exc:  # noqa: BLE001
        return HtfBias(direction="unknown", strength=0.0, source="error", notes=[str(exc)])


def bias_allows_side(bias: HtfBias, side: str, *, strict: bool = False) -> bool:
    """Whether LTF side agrees with HTF direction."""
    d = (bias.direction or "").lower()
    s = (side or "").upper()
    if d in ("", "unknown", "range"):
        return not strict  # range: allow both unless strict
    if d == "up":
        return s in ("CALL", "LONG", "BULL", "")
    if d == "down":
        return s in ("PUT", "SHORT", "BEAR", "")
    return True
