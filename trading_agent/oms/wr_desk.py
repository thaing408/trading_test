"""Auto-desk win-rate gates (chop cash, pullback-only, no 0DTE, time stop).

Master switch: ``TRADING_AGENT_WR_DESK=1`` (default ON).
Disable: ``TRADING_AGENT_WR_DESK=0`` (tests / old export).

LIVE ENTERs then require:
  - process bias ``trade`` (not light/cash)
  - regime not chop/range
  - optional tape: SPY 10d MA >= 20d MA and VIX <= 20
  - method in allowlist (default chart_patterns + fvg/soulz/swing confirms)
  - no bear/PUT
  - DTE >= 3 (index 0DTE off unless WR_ALLOW_INDEX_0DTE=1 *and* tape push)
  - spread < max if provided on the order

Also: multi-method export requires ``chart_patterns`` in play_methods
(``TRADING_AGENT_EXPORT_REQUIRE_CHART_PATTERNS=1``, default ON).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, FrozenSet, Optional, Tuple

from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# Pattern-first allowlist — ORB/0DTE/top_winners stay research-only for LIVE
_DEFAULT_ALLOW = frozenset({"chart_patterns", "fvg", "soulz_pa", "swing_daily"})
_BLOCK_METHODS = frozenset(
    {"orb_vwap", "odte_breakout", "top_winners", "range_fade", "bear_breakdown"}
)
_CHOP = ("chop", "range", "sideways", "neutral", "mean-revert", "mean_revert")


def wr_desk_enabled() -> bool:
    raw = os.getenv("TRADING_AGENT_WR_DESK", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "1" if default else "0").strip().lower()
    if default:
        return raw not in ("0", "false", "no", "off")
    return raw in ("1", "true", "yes", "on")


def allowed_methods() -> FrozenSet[str]:
    raw = os.getenv("TRADING_AGENT_WR_METHODS", "").strip()
    if not raw:
        return _DEFAULT_ALLOW
    parts = {p.strip().lower() for p in raw.split(",") if p.strip()}
    return frozenset(parts) if parts else _DEFAULT_ALLOW


def max_spread_pct() -> float:
    try:
        return float(os.getenv("TRADING_AGENT_WR_MAX_SPREAD_PCT", "8") or 8)
    except ValueError:
        return 8.0


def time_stop_minutes() -> float:
    try:
        return float(os.getenv("TRADING_AGENT_WR_TIME_STOP_MIN", "60") or 60)
    except ValueError:
        return 60.0


def vix_cash_level() -> float:
    try:
        return float(os.getenv("TRADING_AGENT_WR_VIX_CASH", "20") or 20)
    except ValueError:
        return 20.0


def read_tape(*, fetch: bool = True) -> Dict[str, Any]:
    """SPY 10/20 SMA + VIX. Fail-open (unknown) if fetch fails."""
    out: Dict[str, Any] = {
        "ok": False,
        "vix": None,
        "spy_sma10": None,
        "spy_sma20": None,
        "ma_ok": None,
        "vix_ok": None,
        "push": None,
        "error": "",
    }
    if not fetch or not _env_bool("TRADING_AGENT_WR_TAPE", True):
        out["error"] = "tape_disabled"
        return out
    try:
        import yfinance as yf

        spy = yf.Ticker("SPY").history(period="40d", interval="1d")
        vix = yf.Ticker("^VIX").history(period="10d", interval="1d")
        if spy is None or spy.empty or "Close" not in spy:
            out["error"] = "spy_empty"
            return out
        close = spy["Close"].dropna()
        if len(close) < 20:
            out["error"] = "spy_short"
            return out
        sma10 = float(close.tail(10).mean())
        sma20 = float(close.tail(20).mean())
        last_vix = None
        if vix is not None and not vix.empty and "Close" in vix:
            last_vix = float(vix["Close"].dropna().iloc[-1])
        ma_ok = sma10 >= sma20
        vix_ok = last_vix is None or last_vix <= vix_cash_level()
        out.update(
            {
                "ok": True,
                "vix": last_vix,
                "spy_sma10": sma10,
                "spy_sma20": sma20,
                "ma_ok": ma_ok,
                "vix_ok": vix_ok,
                "push": bool(ma_ok and vix_ok),
            }
        )
        return out
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
        return out


def regime_is_chop(regime: str) -> bool:
    text = (regime or "").lower()
    return any(w in text for w in _CHOP)


def process_session_ok(
    *,
    bias: str,
    regime: str,
    tape: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """Hard cash unless bias=trade and tape/regime not chop."""
    b = (bias or "").strip().lower()
    if b == "cash":
        return False, "wr_cash_bias"
    if b == "light":
        return False, "wr_light_bias"
    if b != "trade":
        return False, "wr_bias_not_trade"
    if regime_is_chop(regime):
        return False, "wr_chop_regime"
    if tape and tape.get("ok"):
        if tape.get("push") is False:
            if tape.get("ma_ok") is False:
                return False, "wr_tape_ma10_below_ma20"
            if tape.get("vix_ok") is False:
                return False, f"wr_tape_vix:{tape.get('vix')}"
            return False, "wr_tape_not_push"
    return True, ""


def setup_allowed(order: Any) -> Tuple[bool, str]:
    """Pullback-family only; no bear; block known bleed methods."""
    setup = str(getattr(order, "setup_id", "") or "").lower()
    strategy = str(getattr(order, "strategy", "") or "").lower()
    side = str(getattr(order, "side", "") or "").upper()
    tags = [str(t).lower() for t in (getattr(order, "method_tags", None) or [])]
    blob = " ".join([setup, strategy] + tags)

    if side in ("PUT", "BEAR", "BEARISH", "SHORT") or "bear_breakdown" in blob:
        return False, "wr_no_bear"

    allow = allowed_methods()
    hits = [m for m in allow if m and m in blob]
    blocked = [m for m in _BLOCK_METHODS if m in blob]
    if blocked and not hits:
        return False, f"wr_method_blocked:{blocked[0]}"
    if allow and not hits:
        return False, "wr_method_not_pullback"
    return True, ""


def dte_ok(symbol: str, dte: int, *, tape_push: Optional[bool] = None) -> Tuple[bool, str]:
    if dte < 0:
        return False, "expired"
    allow_0 = _env_bool("TRADING_AGENT_WR_ALLOW_INDEX_0DTE", False)
    idx = str(symbol or "").upper() in {"SPY", "QQQ", "IWM"}
    if dte < 3:
        if allow_0 and idx and dte >= 0 and tape_push is True:
            return True, ""
        return False, f"wr_no_0dte:dte={dte}"
    return True, ""


def spread_ok(order: Any) -> Tuple[bool, str]:
    cap = max_spread_pct()
    if cap <= 0:
        return True, ""
    pct = getattr(order, "bid_ask_spread_pct", None)
    if pct is None and isinstance(getattr(order, "broker_response", None), dict):
        pct = (order.broker_response or {}).get("spread_pct")
    if pct is None:
        return True, ""
    try:
        v = float(pct)
    except (TypeError, ValueError):
        return True, ""
    if v > cap:
        return False, f"wr_spread:{v:.1f}>{cap:.1f}"
    return True, ""


def evaluate_wr_enter(
    order: Any,
    *,
    bias: str = "",
    regime: str = "",
    tape: Optional[Dict[str, Any]] = None,
    dte: Optional[int] = None,
) -> Tuple[bool, str]:
    if not wr_desk_enabled():
        return True, ""
    ok, reason = process_session_ok(bias=bias, regime=regime, tape=tape)
    if not ok:
        return False, reason
    ok, reason = setup_allowed(order)
    if not ok:
        return False, reason
    ok, reason = spread_ok(order)
    if not ok:
        return False, reason
    if dte is not None:
        push = None if not tape else tape.get("push")
        ok, reason = dte_ok(str(getattr(order, "symbol", "") or ""), int(dte), tape_push=push)
        if not ok:
            return False, reason
    return True, ""


def apply_payoff(entry: float, stop: float, *, bullish: bool) -> float:
    """Target 2R (stop distance) so winners can pay for ~50% WR."""
    e, s = float(entry), float(stop)
    r = abs(e - s)
    if r <= 0:
        return e * (1.04 if bullish else 0.96)
    if bullish:
        return e + 2.0 * r
    return e - 2.0 * r


def time_stop_due(lot: Any, *, now: Optional[datetime] = None) -> Tuple[bool, str]:
    if not wr_desk_enabled():
        return False, ""
    mins = time_stop_minutes()
    if mins <= 0:
        return False, ""
    opened = str(getattr(lot, "opened_at", "") or "")
    if not opened:
        return False, ""
    try:
        ts = datetime.fromisoformat(opened.replace("Z", "+00:00"))
    except ValueError:
        return False, ""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    tnow = now or datetime.now(timezone.utc)
    if tnow.tzinfo is None:
        tnow = tnow.replace(tzinfo=timezone.utc)
    age = (tnow - ts).total_seconds() / 60.0
    if age >= mins:
        return True, f"wr_time_stop:{age:.0f}m>={mins:.0f}m"
    return False, ""
