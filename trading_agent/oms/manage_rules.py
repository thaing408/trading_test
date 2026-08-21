"""Multi-day OMS manage rules: EOD/0DTE flatten, min-premium wipe, trail stops.

Used by ``manage_open_lots`` before/alongside classic stop/target checks.
All behavior is env-gated (defaults ON for production safety).
"""

from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

from trading_agent.oms.state import OpenLot

ET = ZoneInfo("America/New_York")


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name, "1" if default else "0").strip().lower()
    if default:
        return raw not in ("0", "false", "no", "off")
    return raw in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


def _env_time(name: str, default: str) -> time:
    raw = (os.getenv(name, default) or default).strip()
    try:
        hh, mm = raw.split(":")[:2]
        return time(int(hh), int(mm))
    except (ValueError, TypeError):
        parts = default.split(":")
        return time(int(parts[0]), int(parts[1]))


def parse_expiration(lot: OpenLot) -> Optional[date]:
    raw = str(lot.expiration or "")[:10]
    if not raw:
        # OCC YYMMDD embedded: ROOT(6)+YYMMDD(6)+C/P+strike
        occ = (lot.occ_symbol or "").replace(" ", "")
        if len(occ) >= 15:
            yymmdd = occ[6:12]
            try:
                yy, mm, dd = int(yymmdd[0:2]), int(yymmdd[2:4]), int(yymmdd[4:6])
                year = 2000 + yy if yy < 80 else 1900 + yy
                return date(year, mm, dd)
            except ValueError:
                return None
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def calendar_dte(lot: OpenLot, *, now: Optional[datetime] = None) -> Optional[int]:
    exp = parse_expiration(lot)
    if exp is None:
        return None
    ts = now or datetime.now(ET)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=ET)
    else:
        ts = ts.astimezone(ET)
    return (exp - ts.date()).days


def eod_0dte_flatten_due(lot: OpenLot, *, now: Optional[datetime] = None) -> Tuple[bool, str]:
    """Flatten 0DTE (and expired) after cutoff ET. Default cutoff 15:45 ET."""
    if not _env_bool("TRADING_AGENT_EOD_0DTE_FLATTEN", True):
        return False, ""
    dte = calendar_dte(lot, now=now)
    if dte is None:
        return False, ""
    if dte < 0:
        return True, "expired_option_flatten"
    if dte > 0:
        return False, ""
    ts = now or datetime.now(ET)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=ET)
    else:
        ts = ts.astimezone(ET)
    cutoff = _env_time("TRADING_AGENT_EOD_0DTE_CUTOFF_ET", "15:45")
    if ts.timetz().replace(tzinfo=None) >= cutoff:
        return True, "eod_0dte_flatten"
    return False, ""


def near_expiry_flatten_due(lot: OpenLot, *, now: Optional[datetime] = None) -> Tuple[bool, str]:
    """Close option lots that expire soon (calendar DTE ≤ max).

    Defaults (production-safe):
    - ``TRADING_AGENT_NEAR_EXPIRY_FLATTEN=1``
    - ``TRADING_AGENT_NEAR_EXPIRY_MAX_DTE=1`` → flatten when DTE is 0 or 1
    - ``TRADING_AGENT_NEAR_EXPIRY_CUTOFF_ET=15:00`` → for DTE=1, start after 15:00 ET
      (0DTE still uses ``TRADING_AGENT_EOD_0DTE_CUTOFF_ET``, default 15:45)

    Expired (DTE < 0) always flatten when this feature is on.
    Equity lots are ignored.
    """
    if not _env_bool("TRADING_AGENT_NEAR_EXPIRY_FLATTEN", True):
        return False, ""
    instr = (lot.instrument or "").lower()
    if instr in ("equity", "underlying", "etf", "stock", "shares"):
        return False, ""
    dte = calendar_dte(lot, now=now)
    if dte is None:
        return False, ""
    if dte < 0:
        return True, "expired_option_flatten"

    max_dte = int(_env_float("TRADING_AGENT_NEAR_EXPIRY_MAX_DTE", 1.0))
    if max_dte < 0:
        max_dte = 0
    if dte > max_dte:
        return False, ""

    ts = now or datetime.now(ET)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=ET)
    else:
        ts = ts.astimezone(ET)
    tnow = ts.timetz().replace(tzinfo=None)

    if dte == 0:
        # Prefer dedicated 0DTE cutoff when that feature is on; else near-expiry cutoff
        if _env_bool("TRADING_AGENT_EOD_0DTE_FLATTEN", True):
            cutoff = _env_time("TRADING_AGENT_EOD_0DTE_CUTOFF_ET", "15:45")
            if tnow >= cutoff:
                return True, "eod_0dte_flatten"
            return False, ""
        cutoff = _env_time("TRADING_AGENT_NEAR_EXPIRY_CUTOFF_ET", "15:00")
        if tnow >= cutoff:
            return True, "near_expiry_flatten:dte=0"
        return False, ""

    # 1 … max_dte : flatten after near-expiry afternoon cutoff
    cutoff = _env_time("TRADING_AGENT_NEAR_EXPIRY_CUTOFF_ET", "15:00")
    if tnow >= cutoff:
        return True, f"near_expiry_flatten:dte={dte}"
    return False, ""


def min_premium_wipe_due(
    lot: OpenLot,
    *,
    option_mark: Optional[float],
    option_entry: Optional[float] = None,
) -> Tuple[bool, str]:
    """Wipe dirt-cheap long option marks (IWM-style). Default floor $0.05."""
    if not _env_bool("TRADING_AGENT_MIN_PREMIUM_WIPE", True):
        return False, ""
    floor = _env_float("TRADING_AGENT_MIN_OPTION_PREMIUM", 0.05)
    if floor <= 0 or option_mark is None:
        return False, ""
    mark = float(option_mark)
    if mark < 0:
        return False, ""
    # Only long debit options
    instr = (lot.instrument or "").lower()
    if instr not in ("options", "option", ""):
        return False, ""
    if mark <= floor:
        # If we know entry and mark never had value, still wipe
        return True, f"min_premium_wipe:{mark:.3f}<={floor:.3f}"
    return False, ""


def _is_bullish(lot: OpenLot) -> bool:
    side = (lot.side or "").lower()
    return side in ("long", "bull", "call", "buy", "bullish")


def _is_bearish(lot: OpenLot) -> bool:
    side = (lot.side or "").lower()
    return side in ("short", "bear", "put", "sell", "bearish")


def update_trail_stop(
    lot: OpenLot,
    *,
    underlying_price: float,
) -> Dict[str, Any]:
    """Raise/lower software trail on underlying; mutates lot.stop / broker_meta.

    Rules (defaults):
      - After price moves ``TRAIL_BE_R`` * initial R in favor → trail to breakeven (entry)
      - Then lock ``TRAIL_LOCK_PCT`` of favorable excursion from entry into stop
    """
    if not _env_bool("TRADING_AGENT_TRAIL_ENABLED", True):
        return {"trailed": False, "reason": "disabled"}
    px = float(underlying_price or 0)
    if px <= 0:
        return {"trailed": False, "reason": "no_price"}

    entry = float(lot.entry or 0)
    stop = float(lot.stop or 0)
    target = float(lot.target or 0)
    if entry <= 0 or stop <= 0:
        return {"trailed": False, "reason": "no_structure"}

    be_r = _env_float("TRADING_AGENT_TRAIL_BE_R", 0.5)  # 0.5R to breakeven
    lock_pct = _env_float("TRADING_AGENT_TRAIL_LOCK_PCT", 50.0) / 100.0
    meta = dict(lot.broker_meta or {})
    initial_stop = float(meta.get("initial_stop") or stop)
    if "initial_stop" not in meta:
        meta["initial_stop"] = initial_stop

    bullish = _is_bullish(lot)
    bearish = _is_bearish(lot)
    if not bullish and not bearish:
        return {"trailed": False, "reason": "neutral_side"}

    changed = False
    trail = float(meta.get("trail_stop_underlying") or 0) or None

    if bullish:
        risk = max(entry - initial_stop, 1e-6)
        favor = px - entry
        # Breakeven once +BE_R * R
        if favor >= be_r * risk:
            new_stop = max(stop, entry)
            # Lock % of run-up
            locked = entry + favor * lock_pct
            new_stop = max(new_stop, locked)
            # Never trail past target
            if target > entry:
                new_stop = min(new_stop, target - 1e-6)
            if new_stop > stop + 1e-6:
                lot.stop = round(new_stop, 4)
                trail = lot.stop
                changed = True
    else:  # bearish
        risk = max(initial_stop - entry, 1e-6)
        favor = entry - px
        if favor >= be_r * risk:
            new_stop = min(stop, entry) if stop > 0 else entry
            locked = entry - favor * lock_pct
            new_stop = min(new_stop, locked)
            if target > 0 and target < entry:
                new_stop = max(new_stop, target + 1e-6)
            if stop <= 0 or new_stop < stop - 1e-6:
                lot.stop = round(new_stop, 4)
                trail = lot.stop
                changed = True

    if trail is not None:
        meta["trail_stop_underlying"] = float(trail)
    meta["trail_updated_at"] = datetime.now(ET).isoformat()
    lot.broker_meta = meta
    if changed:
        lot.status = "protected"
    return {
        "trailed": changed,
        "stop": lot.stop,
        "trail_stop_underlying": meta.get("trail_stop_underlying"),
        "underlying": px,
    }


def early_exit_reasons(
    lot: OpenLot,
    *,
    option_mark: Optional[float] = None,
    option_entry: Optional[float] = None,
    now: Optional[datetime] = None,
) -> Tuple[bool, str]:
    """Priority exits before classic stop/target: near-expiry / 0DTE / min premium."""
    ok, reason = near_expiry_flatten_due(lot, now=now)
    if ok:
        return True, reason
    # Keep dedicated 0DTE helper as fallback if near-expiry feature disabled
    ok, reason = eod_0dte_flatten_due(lot, now=now)
    if ok:
        return True, reason
    ok, reason = min_premium_wipe_due(
        lot, option_mark=option_mark, option_entry=option_entry
    )
    if ok:
        return True, reason
    try:
        from trading_agent.oms.wr_desk import time_stop_due

        ok, reason = time_stop_due(lot, now=now)
        if ok:
            return True, reason
    except Exception:
        pass
    return False, ""


def capture_option_premium(
    lot: OpenLot,
    *,
    premium: Optional[float],
    source: str = "quote",
) -> bool:
    """Persist true-ish option entry premium on the lot (not underlying spot)."""
    if premium is None:
        return False
    try:
        px = float(premium)
    except (TypeError, ValueError):
        return False
    if not (0 < px < 50):
        return False
    meta = dict(lot.broker_meta or {})
    # Prefer first real premium; allow upgrade from backfill_note
    existing = meta.get("option_entry_premium")
    note = str(meta.get("option_entry_premium_note") or "")
    if existing and "backfill" not in note.lower():
        try:
            if float(existing) > 0:
                return False  # keep first fill
        except (TypeError, ValueError):
            pass
    meta["option_entry_premium"] = px
    meta["option_entry_premium_source"] = source
    meta["option_entry_premium_note"] = source
    lot.broker_meta = meta
    # Keep structure entry on lot.entry; fill_entry only if currently looks like und
    if float(lot.fill_entry or 0) >= 50 or float(lot.fill_entry or 0) <= 0:
        # don't overwrite und structure into fill; premium lives in meta
        pass
    return True


def manage_until_et() -> time:
    """Watch/manage end time ET (default 16:00 — covers 0DTE flatten window)."""
    return _env_time("TRADING_AGENT_MANAGE_UNTIL_ET", "16:00")


def in_manage_window(now: Optional[datetime] = None) -> bool:
    """Weekday session from consumer open through manage-until (default 9:25–16:00 ET)."""
    ts = now or datetime.now(ET)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=ET)
    else:
        ts = ts.astimezone(ET)
    if ts.weekday() >= 5:
        return False
    start = _env_time("TRADING_AGENT_CONSUMER_FROM_ET", "09:25")
    end = manage_until_et()
    t = ts.timetz().replace(tzinfo=None)
    return start <= t <= end
