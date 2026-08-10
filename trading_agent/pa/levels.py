"""Key PA levels: PDH/PDL, session H/L, prior close, whole dollars, OR."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from typing import Any, List, Optional, Sequence
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


@dataclass
class KeyLevels:
    last: float
    prior_close: Optional[float] = None
    pdh: Optional[float] = None
    pdl: Optional[float] = None
    session_high: Optional[float] = None
    session_low: Optional[float] = None
    session_open: Optional[float] = None
    or_high: Optional[float] = None
    or_low: Optional[float] = None
    whole_above: List[float] = field(default_factory=list)
    whole_below: List[float] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def whole_dollar_levels(price: float, n: int = 4) -> tuple[List[float], List[float]]:
    import numpy as np

    floor_px = float(np.floor(price))
    ceil_px = float(np.ceil(price))
    if ceil_px == floor_px:
        above = [floor_px + i for i in range(1, n + 1)]
        below = [floor_px - i for i in range(1, n + 1)]
    else:
        above = [ceil_px + i for i in range(0, n)]
        below = [floor_px - i for i in range(0, n)]
    return [float(x) for x in above], [float(x) for x in below]


def _session_days(df) -> List[date]:
    return sorted({ts.date() for ts in df.index})


def compute_key_levels(
    df,
    *,
    or_minutes: int = 30,
    bar_minutes: int = 15,
) -> KeyLevels:
    """Compute classic PA levels from an ET-indexed OHLCV frame."""
    if df is None or len(df) == 0:
        return KeyLevels(last=0.0, notes=["empty df"])

    closes = df["Close"].astype(float)
    last = float(closes.iloc[-1])
    above, below = whole_dollar_levels(last)
    levels = KeyLevels(last=last, whole_above=above, whole_below=below)

    days = _session_days(df)
    if not days:
        return levels
    today = days[-1]
    day_mask = [ts.date() == today for ts in df.index]
    day = df.loc[day_mask]
    if day.empty:
        return levels

    rth = day.between_time(time(9, 30), time(16, 0)) if hasattr(day, "between_time") else day
    use = rth if len(rth) else day
    levels.session_high = float(use["High"].max())
    levels.session_low = float(use["Low"].min())
    levels.session_open = float(use.iloc[0]["Open"])

    # Opening range: first N minutes ≈ n bars
    n_or = max(1, int(round(or_minutes / max(bar_minutes, 1))))
    head = use.iloc[:n_or]
    if len(head):
        levels.or_high = float(head["High"].max())
        levels.or_low = float(head["Low"].min())

    if len(days) >= 2:
        prev = days[-2]
        prev_mask = [ts.date() == prev for ts in df.index]
        prev_df = df.loc[prev_mask]
        if len(prev_df):
            pr = prev_df.between_time(time(9, 30), time(16, 0)) if hasattr(prev_df, "between_time") else prev_df
            use_p = pr if len(pr) else prev_df
            levels.pdh = float(use_p["High"].max())
            levels.pdl = float(use_p["Low"].min())
            levels.prior_close = float(use_p["Close"].iloc[-1])
            levels.notes.append(f"prior session {prev.isoformat()}")

    levels.notes.append(f"session {today.isoformat()}")
    return levels
