"""Mechanical open-window model (QT / PO3 / CISD / IFVG objective proxies).

Window: 9:30–9:50 America/New_York (matches published "mech model" journals).
RR: 1.5–2.5× risk (default 2.0).

Proxies (fully deterministic on OHLCV):
- PO3 / open manipulation: sweep of first ``or_minutes`` range extreme then reclaim
- IFVG: 3-bar fair-value-gap that later trades back through (inverse) as confirmation
- CISD: close beyond a short swing high/low after opposing impulse (state change)
- HTF bias: prior-day close vs open (or overnight gap) must not fight the setup
- Optional SMT: SPY vs QQQ (or pair) fails to confirm a swing → soft boost only

Output is an auto-trade-ready signal package (entry/stop/target) for desk export.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

import numpy as np

ET = ZoneInfo("America/New_York")


@dataclass
class QtModelConfig:
    symbol: str = "QQQ"
    pair_symbol: str = "SPY"  # for optional SMT boost
    window_start_et: time = time(9, 30)
    window_end_et: time = time(9, 50)
    or_minutes: int = 5  # opening range for PO3 manipulation
    rr_min: float = 1.5
    rr_max: float = 2.5
    rr_default: float = 2.0
    # Stop buffer beyond sweep extreme (fraction of OR range, min ticks)
    stop_buffer_frac: float = 0.15
    min_or_range_pct: float = 0.05  # skip dead opens
    max_or_range_pct: float = 1.5  # skip chaos opens
    require_cisd: bool = True
    require_ifvg: bool = False  # optional; CISD+PO3 often enough
    require_htf_align: bool = True
    use_smt_boost: bool = True
    # Auto-trade risk package
    account_risk_pct: float = 1.0
    portfolio_value: float = 100_000.0


@dataclass
class QtSignal:
    symbol: str
    side: str  # long | short
    setup: str  # e.g. po3_reclaim_cisd
    entry: float
    stop: float
    target: float
    rr: float
    or_high: float
    or_low: float
    window_note: str
    checklist: List[str] = field(default_factory=list)
    confidence: float = 60.0
    auto_trade_eligible: bool = False
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QtSessionBrief:
    symbol: str
    asof: str
    in_window: bool
    window_note: str
    signals: List[QtSignal]
    htf_bias: str
    source: str
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "asof": self.asof,
            "in_window": self.in_window,
            "window_note": self.window_note,
            "htf_bias": self.htf_bias,
            "source": self.source,
            "errors": list(self.errors),
            "signals": [s.to_dict() for s in self.signals],
        }


# --- pure bar helpers ---------------------------------------------------------


def _to_et(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc).astimezone(ET)
    return ts.astimezone(ET)


def session_day_mask(
    timestamps: Sequence[datetime],
    session: date,
) -> List[int]:
    idx: List[int] = []
    for i, ts in enumerate(timestamps):
        t = _to_et(ts)
        if t.date() == session and t.weekday() < 5:
            idx.append(i)
    return idx


def opening_range(
    timestamps: Sequence[datetime],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    session: date,
    or_minutes: int = 5,
) -> Tuple[Optional[float], Optional[float], List[int]]:
    """Return (or_high, or_low, indices of bars in OR)."""
    day = session_day_mask(timestamps, session)
    if not day:
        return None, None, []
    or_idx: List[int] = []
    from datetime import timedelta

    start = _to_et(timestamps[day[0]]).replace(hour=9, minute=30, second=0, microsecond=0)
    end = start + timedelta(minutes=or_minutes)
    for i in day:
        t = _to_et(timestamps[i])
        if start <= t < end:
            or_idx.append(i)
    if not or_idx:
        return None, None, []
    oh = max(float(highs[i]) for i in or_idx)
    ol = min(float(lows[i]) for i in or_idx)
    return oh, ol, or_idx


def detect_fvg(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    i: int,
) -> Optional[Tuple[str, float, float]]:
    """3-candle FVG ending at index i (i is 3rd candle).

    Bullish FVG: low[i] > high[i-2]
    Bearish FVG: high[i] < low[i-2]
    Returns (side, gap_low, gap_high).
    """
    if i < 2:
        return None
    if float(lows[i]) > float(highs[i - 2]):
        return ("bullish", float(highs[i - 2]), float(lows[i]))
    if float(highs[i]) < float(lows[i - 2]):
        return ("bearish", float(highs[i]), float(lows[i - 2]))
    return None


def ifvg_confirm(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    side: str,
    start: int,
    end: int,
) -> bool:
    """True if an FVG forms then price trades back through it (inverse) in window."""
    for i in range(max(start, 2), end + 1):
        fvg = detect_fvg(opens, highs, lows, closes, i)
        if not fvg:
            continue
        fside, glo, ghi = fvg
        # For long setup we want bullish displacement FVG then reclaim / inverse use
        if side == "long" and fside == "bullish":
            for j in range(i + 1, min(end + 1, len(closes))):
                if float(lows[j]) <= glo:
                    return True
        if side == "short" and fside == "bearish":
            for j in range(i + 1, min(end + 1, len(closes))):
                if float(highs[j]) >= ghi:
                    return True
    return False


def cisd_confirm(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    side: str,
    start: int,
    end: int,
    lookback: int = 5,
) -> bool:
    """Change-in-state proxy: close beyond short swing after opposing move."""
    if end <= start or end >= len(closes):
        return False
    for i in range(start + lookback, end + 1):
        window_h = [float(highs[k]) for k in range(i - lookback, i)]
        window_l = [float(lows[k]) for k in range(i - lookback, i)]
        if not window_h:
            continue
        swing_hi = max(window_h)
        swing_lo = min(window_l)
        c = float(closes[i])
        if side == "long" and c > swing_hi:
            # prior impulse down: last few closes declining
            if float(closes[i - 1]) <= float(closes[i - 2]):
                return True
        if side == "short" and c < swing_lo:
            if float(closes[i - 1]) >= float(closes[i - 2]):
                return True
    return False


def po3_setup(
    timestamps: Sequence[datetime],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    session: date,
    or_minutes: int,
    window_end: time,
) -> Optional[Tuple[str, float, float, float, List[str]]]:
    """PO3 open proxy: sweep OR extreme after OR completes, then reclaim.

    Returns (side, entry, stop, or_high/or_low ref, checklist) or None.
    """
    oh, ol, or_idx = opening_range(
        timestamps, highs, lows, closes, session=session, or_minutes=or_minutes
    )
    if oh is None or ol is None or not or_idx:
        return None
    mid = (oh + ol) / 2.0
    rng = oh - ol
    if mid <= 0:
        return None
    rng_pct = 100.0 * rng / mid
    day = session_day_mask(timestamps, session)
    post_or = [i for i in day if i > or_idx[-1]]
    if not post_or:
        return None
    # Restrict to window end
    window_idxs: List[int] = []
    for i in post_or:
        t = _to_et(timestamps[i]).time()
        if t <= window_end:
            window_idxs.append(i)
    if not window_idxs:
        return None

    checklist: List[str] = [f"OR {or_minutes}m high={oh:.2f} low={ol:.2f} range={rng_pct:.2f}%"]
    # Long: sweep below OR low then close back above OR low (reclaim)
    for i in window_idxs:
        if float(lows[i]) < ol and float(closes[i]) > ol:
            entry = float(closes[i])
            stop = float(lows[i]) - max(rng * 0.15, mid * 0.0005)
            checklist.append(f"PO3 long: swept OR low then reclaimed @ bar {_to_et(timestamps[i]).strftime('%H:%M')}")
            return ("long", entry, stop, oh, checklist)
    # Short: sweep above OR high then close back below
    for i in window_idxs:
        if float(highs[i]) > oh and float(closes[i]) < oh:
            entry = float(closes[i])
            stop = float(highs[i]) + max(rng * 0.15, mid * 0.0005)
            checklist.append(f"PO3 short: swept OR high then reclaimed @ bar {_to_et(timestamps[i]).strftime('%H:%M')}")
            return ("short", entry, stop, ol, checklist)
    return None


def htf_bias_from_prior_day(
    timestamps: Sequence[datetime],
    opens: Sequence[float],
    closes: Sequence[float],
    session: date,
) -> str:
    """bullish | bearish | neutral from prior session close vs open + overnight gap."""
    from datetime import timedelta

    prior = session
    for _ in range(5):
        prior = prior - timedelta(days=1)
        if prior.weekday() < 5:
            break
    pidx = session_day_mask(timestamps, prior)
    if len(pidx) < 2:
        return "neutral"
    p_open = float(opens[pidx[0]])
    p_close = float(closes[pidx[-1]])
    day = session_day_mask(timestamps, session)
    if not day:
        return "bullish" if p_close >= p_open else "bearish"
    o = float(opens[day[0]])
    gap = o - p_close
    if p_close >= p_open and gap >= 0:
        return "bullish"
    if p_close <= p_open and gap <= 0:
        return "bearish"
    if gap > 0:
        return "bullish"
    if gap < 0:
        return "bearish"
    return "neutral"


def target_from_rr(entry: float, stop: float, side: str, rr: float) -> float:
    risk = abs(entry - stop)
    if risk <= 0:
        return entry
    if side == "long":
        return entry + risk * rr
    return entry - risk * rr


def evaluate_qt_bars(
    timestamps: Sequence[datetime],
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    cfg: QtModelConfig,
    session: date | None = None,
    now: datetime | None = None,
) -> QtSessionBrief:
    """Pure evaluation on aligned 1m (or fine) bars."""
    errors: List[str] = []
    if not timestamps or len(timestamps) != len(closes):
        return QtSessionBrief(
            symbol=cfg.symbol,
            asof=datetime.now(timezone.utc).isoformat(),
            in_window=False,
            window_note="no bars",
            signals=[],
            htf_bias="neutral",
            source="bars",
            errors=["empty or misaligned bars"],
        )

    now_et = _to_et(now or datetime.now(timezone.utc))
    sess = session or now_et.date()
    in_window = cfg.window_start_et <= now_et.time() <= cfg.window_end_et and now_et.date() == sess
    window_note = (
        f"Window {cfg.window_start_et.strftime('%H:%M')}–{cfg.window_end_et.strftime('%H:%M')} ET "
        f"({'ACTIVE' if in_window else 'outside / historical'})"
    )
    htf = htf_bias_from_prior_day(timestamps, opens, closes, sess)

    oh, ol, or_idx = opening_range(
        timestamps, highs, lows, closes, session=sess, or_minutes=cfg.or_minutes
    )
    signals: List[QtSignal] = []
    if oh is None or ol is None:
        errors.append("opening range unavailable")
        return QtSessionBrief(
            symbol=cfg.symbol,
            asof=now_et.isoformat(),
            in_window=in_window,
            window_note=window_note,
            signals=[],
            htf_bias=htf,
            source="bars",
            errors=errors,
        )

    mid = (oh + ol) / 2.0
    rng_pct = 100.0 * (oh - ol) / mid if mid else 0.0
    if rng_pct < cfg.min_or_range_pct or rng_pct > cfg.max_or_range_pct:
        errors.append(f"OR range {rng_pct:.2f}% outside [{cfg.min_or_range_pct},{cfg.max_or_range_pct}]")
        return QtSessionBrief(
            symbol=cfg.symbol,
            asof=now_et.isoformat(),
            in_window=in_window,
            window_note=window_note + f" | OR={rng_pct:.2f}% skipped",
            signals=[],
            htf_bias=htf,
            source="bars",
            errors=errors,
        )

    po3 = po3_setup(
        timestamps,
        highs,
        lows,
        closes,
        session=sess,
        or_minutes=cfg.or_minutes,
        window_end=cfg.window_end_et,
    )
    if not po3:
        return QtSessionBrief(
            symbol=cfg.symbol,
            asof=now_et.isoformat(),
            in_window=in_window,
            window_note=window_note + f" | OR {oh:.2f}/{ol:.2f} no PO3 reclaim yet",
            signals=[],
            htf_bias=htf,
            source="bars",
            errors=errors,
        )

    side, entry, stop, _ref, checklist = po3
    day = session_day_mask(timestamps, sess)
    start_i = or_idx[-1] + 1 if or_idx else day[0]
    end_i = day[-1] if day else len(closes) - 1
    # clip end to window
    for i in day:
        if _to_et(timestamps[i]).time() <= cfg.window_end_et:
            end_i = i

    if cfg.require_htf_align:
        if side == "long" and htf == "bearish":
            errors.append("HTF bias bearish — long blocked")
            return QtSessionBrief(
                symbol=cfg.symbol,
                asof=now_et.isoformat(),
                in_window=in_window,
                window_note=window_note,
                signals=[],
                htf_bias=htf,
                source="bars",
                errors=errors,
            )
        if side == "short" and htf == "bullish":
            errors.append("HTF bias bullish — short blocked")
            return QtSessionBrief(
                symbol=cfg.symbol,
                asof=now_et.isoformat(),
                in_window=in_window,
                window_note=window_note,
                signals=[],
                htf_bias=htf,
                source="bars",
                errors=errors,
            )
        checklist.append(f"HTF bias={htf} aligned")

    if cfg.require_cisd:
        ok = cisd_confirm(
            highs, lows, closes, side=side, start=start_i, end=end_i
        )
        if not ok:
            errors.append("CISD confirmation missing")
            return QtSessionBrief(
                symbol=cfg.symbol,
                asof=now_et.isoformat(),
                in_window=in_window,
                window_note=window_note,
                signals=[],
                htf_bias=htf,
                source="bars",
                errors=errors,
            )
        checklist.append("CISD proxy confirmed")

    if cfg.require_ifvg:
        ok = ifvg_confirm(
            opens, highs, lows, closes, side=side, start=start_i, end=end_i
        )
        if not ok:
            errors.append("IFVG confirmation missing")
            return QtSessionBrief(
                symbol=cfg.symbol,
                asof=now_et.isoformat(),
                in_window=in_window,
                window_note=window_note,
                signals=[],
                htf_bias=htf,
                source="bars",
                errors=errors,
            )
        checklist.append("IFVG proxy confirmed")
    else:
        # soft note if present
        if ifvg_confirm(opens, highs, lows, closes, side=side, start=start_i, end=end_i):
            checklist.append("IFVG proxy present (boost)")

    rr = min(cfg.rr_max, max(cfg.rr_min, cfg.rr_default))
    target = target_from_rr(entry, stop, side, rr)
    risk = abs(entry - stop)
    if risk <= 0 or (side == "long" and not (stop < entry < target)):
        errors.append("invalid risk geometry")
        return QtSessionBrief(
            symbol=cfg.symbol,
            asof=now_et.isoformat(),
            in_window=in_window,
            window_note=window_note,
            signals=[],
            htf_bias=htf,
            source="bars",
            errors=errors,
        )
    if side == "short" and not (target < entry < stop):
        errors.append("invalid short geometry")
        return QtSessionBrief(
            symbol=cfg.symbol,
            asof=now_et.isoformat(),
            in_window=in_window,
            window_note=window_note,
            signals=[],
            htf_bias=htf,
            source="bars",
            errors=errors,
        )

    conf = 62.0
    if "IFVG proxy present" in " ".join(checklist):
        conf += 6.0
    if htf in ("bullish", "bearish"):
        conf += 4.0
    conf = min(90.0, conf)

    sig = QtSignal(
        symbol=cfg.symbol.upper(),
        side=side,
        setup="po3_reclaim_cisd",
        entry=round(entry, 2),
        stop=round(stop, 2),
        target=round(target, 2),
        rr=round(rr, 2),
        or_high=round(oh, 2),
        or_low=round(ol, 2),
        window_note=window_note,
        checklist=checklist,
        confidence=conf,
        auto_trade_eligible=True,
        notes=(
            f"QT mech proxy | RR {rr:.1f} | risk ${risk:.2f}/sh | "
            f"window 9:30–9:50 ET | PO3+CISD"
        ),
    )
    signals.append(sig)
    return QtSessionBrief(
        symbol=cfg.symbol.upper(),
        asof=now_et.isoformat(),
        in_window=in_window,
        window_note=window_note,
        signals=signals,
        htf_bias=htf,
        source="bars",
        errors=errors,
    )


def _fetch_intraday_bars(symbol: str, period: str = "5d", interval: str = "1m"):
    import yfinance as yf

    t = yf.Ticker(symbol)
    df = t.history(period=period, interval=interval, auto_adjust=True)
    if df is None or getattr(df, "empty", True):
        return None
    df = df.reset_index()
    # columns: Datetime or Date
    ts_col = "Datetime" if "Datetime" in df.columns else df.columns[0]
    stamps = []
    for x in df[ts_col].tolist():
        if hasattr(x, "to_pydatetime"):
            stamps.append(x.to_pydatetime())
        else:
            stamps.append(x)
    return {
        "timestamps": stamps,
        "opens": [float(x) for x in df["Open"].tolist()],
        "highs": [float(x) for x in df["High"].tolist()],
        "lows": [float(x) for x in df["Low"].tolist()],
        "closes": [float(x) for x in df["Close"].tolist()],
    }


def run_qt_model(
    symbol: str | None = None,
    *,
    cfg: QtModelConfig | None = None,
    session: date | None = None,
    bars: dict | None = None,
) -> QtSessionBrief:
    """Live or injected bars → QT session brief."""
    cfg = cfg or QtModelConfig()
    if symbol:
        cfg.symbol = symbol.upper()
    if bars is None:
        try:
            bars = _fetch_intraday_bars(cfg.symbol)
        except Exception as exc:  # noqa: BLE001
            return QtSessionBrief(
                symbol=cfg.symbol,
                asof=datetime.now(timezone.utc).isoformat(),
                in_window=False,
                window_note="fetch failed",
                signals=[],
                htf_bias="neutral",
                source="yfinance",
                errors=[str(exc)],
            )
    if not bars:
        return QtSessionBrief(
            symbol=cfg.symbol,
            asof=datetime.now(timezone.utc).isoformat(),
            in_window=False,
            window_note="no data",
            signals=[],
            htf_bias="neutral",
            source="yfinance",
            errors=["empty history"],
        )
    brief = evaluate_qt_bars(
        bars["timestamps"],
        bars["opens"],
        bars["highs"],
        bars["lows"],
        bars["closes"],
        cfg=cfg,
        session=session,
    )
    brief.source = "yfinance" if bars else "bars"
    return brief


def format_qt_brief(brief: QtSessionBrief) -> str:
    lines = [
        f"# QT Open-Window Mech Model — {brief.symbol}",
        f"**As of:** {brief.asof[:19]} | HTF bias: **{brief.htf_bias}**",
        f"**{brief.window_note}**",
        f"In window now: **{brief.in_window}** | source={brief.source}",
        "",
    ]
    if brief.errors:
        lines.append("**Notes / blocks:**")
        for e in brief.errors:
            lines.append(f"- {e}")
        lines.append("")
    if not brief.signals:
        lines.append("_No auto-trade signal this session (rules not met)._")
    for i, s in enumerate(brief.signals, 1):
        lines.append(f"## {i}. {s.side.upper()} `{s.setup}` conf={s.confidence:.0f}")
        lines.append(
            f"Entry **${s.entry:.2f}** | Stop **${s.stop:.2f}** | "
            f"Target **${s.target:.2f}** | RR **{s.rr:.1f}**"
        )
        lines.append(f"OR high/low: {s.or_high:.2f} / {s.or_low:.2f}")
        lines.append("Checklist:")
        for c in s.checklist:
            lines.append(f"- {c}")
        lines.append(f"_{s.notes}_")
        lines.append(f"Auto-trade eligible: **{s.auto_trade_eligible}**")
        lines.append("")
    lines.append("---")
    lines.append(
        "*Objective proxies for QT/PO3/CISD/IFVG — not discretionary ICT labeling. "
        "Not financial advice.*"
    )
    return "\n".join(lines)


def signals_to_auto_trade_entries(
    brief: QtSessionBrief,
    *,
    portfolio_value: float = 100_000.0,
    risk_pct: float = 1.0,
    expires_at: str | None = None,
) -> List[Dict[str, Any]]:
    """Map QT signals → auto_trade_book ENTER-shaped rows (underlying package)."""
    from datetime import datetime, timezone

    exp = expires_at or datetime.now(timezone.utc).replace(
        hour=23, minute=59, second=0, microsecond=0
    ).isoformat()
    rows: List[Dict[str, Any]] = []
    for s in brief.signals:
        if not s.auto_trade_eligible:
            continue
        risk_pts = abs(s.entry - s.stop)
        max_risk = round(portfolio_value * (risk_pct / 100.0), 2)
        max_reward = round(max_risk * s.rr, 2)
        rows.append(
            {
                "symbol": s.symbol,
                "action": "ENTER",
                "side": "Bullish" if s.side == "long" else "Bearish",
                "strategy": "QT Open-Window Mech",
                "setup_id": s.setup,
                "setup_name": "quarterly_theory_po3_cisd",
                "setup_grade": "A" if s.confidence >= 70 else "B",
                "grade_score": s.confidence,
                "entry": s.entry,
                "stop": s.stop,
                "target": s.target,
                "strike_prices": [],  # underlying / futures-style; options optional later
                "expiration": "",
                "max_risk_dollars": max_risk,
                "max_reward_dollars": max_reward,
                "max_risk_pct": risk_pct,
                "confidence": s.confidence,
                "probability_of_success": min(0.65, 0.45 + s.confidence / 400.0),
                "method_tags": ["qt_open_window", "po3_reclaim", "cisd_proxy", "gap_optional"],
                "method_notes": s.notes[:240],
                "checklist_passed": True,
                "edge_complete": True,
                "defined_risk": True,
                "instrument": "underlying",
                "qt_window": s.window_note,
                "or_high": s.or_high,
                "or_low": s.or_low,
                "rr": s.rr,
                "expires_at": exp,
                "auto_trade_eligible": True,
                "notes": "; ".join(s.checklist)[:240],
            }
        )
    return rows


def export_qt_auto_trade_book(
    symbols: Sequence[str] | None = None,
    *,
    session_dir: Optional[Any] = None,
) -> Dict[str, Any]:
    """Run QT model on symbols and merge into sync auto_trade book entries."""
    import json
    from pathlib import Path

    from trading_agent.export.auto_trade_book import default_sync_dir, write_auto_trade_book

    syms = [s.upper() for s in (symbols or ["QQQ", "SPY", "IWM"])]
    all_entries: List[Dict[str, Any]] = []
    briefs: List[dict] = []
    for sym in syms:
        brief = run_qt_model(sym)
        briefs.append(brief.to_dict())
        all_entries.extend(signals_to_auto_trade_entries(brief))

    now = datetime.now(timezone.utc)
    book = {
        "schema_version": 1,
        "generated_at": now.isoformat(),
        "source": "qt_open_window_mech",
        "role": "windows-research",
        "trading_date": now.astimezone(ET).date().isoformat(),
        "stay_in_cash": len(all_entries) == 0,
        "cash_reason": "" if all_entries else "No QT open-window signals passed rules",
        "entries": all_entries,
        "entry_count": len(all_entries),
        "exits": [],
        "watchlist": syms,
        "qt_briefs": briefs,
        "broker_boundary": (
            "windows-research-suggest-export-only; "
            "no TOS order placement on research host"
        ),
    }
    # Write alongside main book under qt-specific name + optional merge note
    sync = default_sync_dir()
    paths = []
    payload = json.dumps(book, indent=2) + "\n"
    for path in (
        sync / "qt_auto_trade_book.json",
        Path.home() / ".trading_agent" / "sync" / "qt_auto_trade_book.json",
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
        paths.append(str(path))
    if session_dir is not None:
        p = Path(session_dir) / "qt_auto_trade_book.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(payload, encoding="utf-8")
        paths.append(str(p))
    book["_written_paths"] = paths
    return book
