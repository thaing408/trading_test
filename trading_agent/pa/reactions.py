"""Acceptance / rejection at a price level."""

from __future__ import annotations

from typing import Sequence


def rejection_at_level(
    high: float,
    low: float,
    open_: float,
    close: float,
    level: float,
    *,
    tol_pct: float = 0.15,
    side: str = "long",
) -> bool:
    """Wick through/near level + close back on the trade side of the level.

    long: low tags level (or slightly through), close > level and preferably > open
    short: high tags level, close < level
    """
    if level <= 0:
        return False
    tol = level * (tol_pct / 100.0)
    if side in ("long", "CALL", "bull", "bullish"):
        tagged = low <= level + tol
        reclaimed = close > level - tol * 0.25
        return tagged and reclaimed and close >= open_
    if side in ("short", "PUT", "bear", "bearish"):
        tagged = high >= level - tol
        rejected = close < level + tol * 0.25
        return tagged and rejected and close <= open_
    return False


def acceptance_at_level(
    close: float,
    level: float,
    *,
    side: str = "long",
    buffer_pct: float = 0.05,
) -> bool:
    """Close held beyond level (acceptance of new prices)."""
    if level <= 0:
        return False
    buf = level * (buffer_pct / 100.0)
    if side in ("long", "CALL", "bull", "bullish"):
        return close > level + buf
    if side in ("short", "PUT", "bear", "bearish"):
        return close < level - buf
    return False


def series_rejection(
    highs: Sequence[float],
    lows: Sequence[float],
    opens: Sequence[float],
    closes: Sequence[float],
    i: int,
    level: float,
    *,
    side: str = "long",
    tol_pct: float = 0.15,
) -> bool:
    if i < 0 or i >= len(closes):
        return False
    return rejection_at_level(
        float(highs[i]),
        float(lows[i]),
        float(opens[i]) if opens else float(closes[i - 1] if i else closes[i]),
        float(closes[i]),
        level,
        tol_pct=tol_pct,
        side=side,
    )
