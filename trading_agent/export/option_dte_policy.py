"""Dual-path option DTE policy for multi-method auto-trade.

- Index ETFs (default SPY, QQQ, IWM): 0DTE allowed on session weekdays.
- All other symbols: DTE must be > 2 (min_dte = 3 calendar days).

Used at export (pick expiration) and place-time (precheck) so book and broker agree.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import FrozenSet, Optional, Tuple
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

_DEFAULT_0DTE = frozenset({"SPY", "QQQ", "IWM"})


def _parse_symbol_set(raw: str, default: FrozenSet[str]) -> FrozenSet[str]:
    parts = [p.strip().upper() for p in (raw or "").split(",") if p.strip()]
    return frozenset(parts) if parts else default


def index_0dte_symbols() -> FrozenSet[str]:
    return _parse_symbol_set(
        os.getenv("TRADING_AGENT_0DTE_SYMBOLS", "SPY,QQQ,IWM"),
        _DEFAULT_0DTE,
    )


def is_index_0dte_allowed(symbol: str) -> bool:
    return str(symbol or "").strip().upper() in index_0dte_symbols()


def non_index_min_dte() -> int:
    """Min DTE for non-index names. Default 3 means strictly > 2 DTE."""
    try:
        v = int(os.getenv("TRADING_AGENT_NON_INDEX_MIN_DTE", "3") or 3)
    except ValueError:
        v = 3
    return max(1, v)


def min_dte_for_symbol(symbol: str) -> int:
    if is_index_0dte_allowed(symbol):
        return 0
    # Legacy global floor (if set) can only raise non-index min, not lower below 3 default
    base = non_index_min_dte()
    try:
        legacy = int(os.getenv("TRADING_AGENT_MIN_OPTION_DTE", "") or "0")
    except ValueError:
        legacy = 0
    try:
        ibkr_floor = int(os.getenv("IBKR_MIN_OPTION_DTE", "") or "0")
    except ValueError:
        ibkr_floor = 0
    return max(base, legacy, ibkr_floor)


def dte_policy_label(symbol: str) -> str:
    return "index_0dte" if is_index_0dte_allowed(symbol) else f"equity_min_{min_dte_for_symbol(symbol)}"


def _next_weekday(day: date) -> date:
    d = day
    for _ in range(10):
        if d.weekday() < 5:
            return d
        d += timedelta(days=1)
    return day + timedelta(days=1)


def _next_friday_on_or_after(day: date) -> date:
    d = day
    for _ in range(14):
        if d.weekday() == 4:  # Friday
            return d
        d += timedelta(days=1)
    return day + timedelta(days=(4 - day.weekday()) % 7)


def pick_option_expiration(
    symbol: str,
    *,
    from_day: Optional[date] = None,
) -> date:
    """Choose option expiration date for symbol under dual-path DTE policy."""
    asof = from_day or datetime.now(ET).date()
    min_dte = min_dte_for_symbol(symbol)

    if min_dte <= 0:
        # 0DTE indexes: today if weekday, else next session day
        if asof.weekday() < 5:
            return asof
        return _next_weekday(asof + timedelta(days=1))

    # Equity / non-index: first eligible day is asof + min_dte
    earliest = asof + timedelta(days=min_dte)
    earliest = _next_weekday(earliest)
    # Prefer Friday weekly when it is within a week of earliest and still ≥ min_dte
    fri = _next_friday_on_or_after(earliest)
    if (fri - asof).days <= min_dte + 7:
        return fri
    return earliest


def calendar_dte(exp: date, *, asof: Optional[date] = None) -> int:
    day = asof or datetime.now(ET).date()
    return (exp - day).days


def dte_allowed(
    symbol: str,
    exp: date,
    *,
    asof: Optional[date] = None,
) -> Tuple[bool, str, int]:
    """Return (ok, reason, dte). reason empty when ok."""
    dte = calendar_dte(exp, asof=asof)
    if dte < 0:
        return False, "expired", dte
    need = min_dte_for_symbol(symbol)
    if dte < need:
        return False, f"dte_too_short:{dte}<{need}", dte
    try:
        max_dte = int(os.getenv("TRADING_AGENT_MAX_OPTION_DTE", "90") or 90)
    except ValueError:
        max_dte = 90
    if dte > max_dte:
        return False, f"dte_too_long:{dte}", dte
    return True, "", dte
