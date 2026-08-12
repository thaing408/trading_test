"""Historical backtest for Venom Model v1 (QQQ / SPY focused)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional, Sequence
from zoneinfo import ZoneInfo

import numpy as np

from trading_agent.pa.venom import (
    ET,
    SESSION_END,
    compute_venom_box,
    scan_venom_signals,
)
from trading_agent.strategy.multi_method import fetch_bars

RTH_END = time(16, 0)


@dataclass
class VenomTrade:
    symbol: str
    day: str
    side: str
    entry_type: str
    entry_time: str
    exit_time: str
    entry: float
    exit: float
    stop: float
    target: float
    exit_reason: str
    pnl_r: float
    notes: str = ""


@dataclass
class VenomBacktestResult:
    symbol: str
    interval: str
    period: str
    days: int
    trade_count: int
    winners: int
    losers: int
    win_rate: float
    total_r: float
    expectancy_r: float
    trades: List[VenomTrade] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


def _session_days(timestamps: Sequence) -> List[date]:
    days = set()
    for ts in timestamps:
        if getattr(ts, "tzinfo", None) is None:
            try:
                ts = ts.tz_localize(ET)
            except Exception:
                pass
        try:
            d = ts.tz_convert(ET).date() if hasattr(ts, "tz_convert") else ts.astimezone(ET).date()
        except Exception:
            d = ts.date() if hasattr(ts, "date") else date.today()
        days.add(d)
    return sorted(days)


def _simulate_exit(
    side: str,
    entry: float,
    stop: float,
    target: float,
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    times: Sequence,
) -> tuple[float, str, Any]:
    for j in range(len(closes)):
        h, l, c = float(highs[j]), float(lows[j]), float(closes[j])
        if side == "CALL":
            if l <= stop:
                return stop, "stop", times[j]
            if h >= target:
                return target, "target", times[j]
        else:
            if h >= stop:
                return stop, "stop", times[j]
            if l <= target:
                return target, "target", times[j]
    # time exit last close
    return float(closes[-1]), "time", times[-1]


def run_venom_backtest(
    symbol: str = "QQQ",
    *,
    period: str = "59d",
    interval: str = "5m",
    source: str = "yfinance",
    r_multiple: float = 2.0,
    require_structure: bool = True,
    df=None,
) -> VenomBacktestResult:
    """Backtest Venom v1 on one symbol (underlying R multiples, not options)."""
    sym = symbol.upper().strip()
    if df is None:
        # Prefer extended hours so 08:00–09:30 exists on equities
        try:
            import yfinance as yf

            t = yf.Ticker(sym)
            # yfinance: prepost=True for premarket
            raw = t.history(period=period, interval=interval, auto_adjust=True, prepost=True)
            if raw is None or raw.empty:
                raw = fetch_bars(sym, period=period, interval=interval, source=source)
            df = raw
        except Exception:
            df = fetch_bars(sym, period=period, interval=interval, source=source)

    df = df.copy()
    # normalize tz
    idx = df.index
    if getattr(idx, "tz", None) is None:
        try:
            df.index = idx.tz_localize(ET)
        except Exception:
            try:
                df.index = idx.tz_localize("UTC").tz_convert(ET)
            except Exception:
                pass
    else:
        df.index = idx.tz_convert(ET)

    opens = df["Open"].astype(float).tolist() if "Open" in df.columns else df["Close"].astype(float).tolist()
    highs = df["High"].astype(float).tolist()
    lows = df["Low"].astype(float).tolist()
    closes = df["Close"].astype(float).tolist()
    times = list(df.index)

    days = _session_days(times)
    trades: List[VenomTrade] = []
    days_with_box = 0
    days_with_signal = 0

    for d in days:
        box = compute_venom_box(times, highs, lows, d)
        if box is None:
            continue
        days_with_box += 1
        sigs = scan_venom_signals(
            times,
            opens,
            highs,
            lows,
            closes,
            d,
            r_multiple=r_multiple,
            require_bpr=False,
            require_structure=require_structure,
            max_entries=1,
        )
        if not sigs:
            continue
        days_with_signal += 1
        sig = sigs[0]
        # path after signal bar same day until RTH end
        path_i = []
        for j in range(sig.index + 1, len(times)):
            et = times[j]
            try:
                t = et.tz_convert(ET) if hasattr(et, "tz_convert") else et
                if t.date() != d:
                    break
                if t.time() > RTH_END:
                    break
            except Exception:
                pass
            path_i.append(j)
        if not path_i:
            continue
        ph = [highs[j] for j in path_i]
        pl = [lows[j] for j in path_i]
        pc = [closes[j] for j in path_i]
        pt = [times[j] for j in path_i]
        exit_px, reason, exit_tm = _simulate_exit(
            sig.side, sig.entry, sig.stop, sig.target, ph, pl, pc, pt
        )
        risk = abs(sig.entry - sig.stop) or 1e-9
        if sig.side == "CALL":
            pnl_r = (exit_px - sig.entry) / risk
        else:
            pnl_r = (sig.entry - exit_px) / risk
        entry_tm = times[sig.index]
        trades.append(
            VenomTrade(
                symbol=sym,
                day=d.isoformat(),
                side=sig.side,
                entry_type=sig.entry_type,
                entry_time=str(entry_tm),
                exit_time=str(exit_tm),
                entry=sig.entry,
                exit=round(exit_px, 4),
                stop=sig.stop,
                target=sig.target,
                exit_reason=reason,
                pnl_r=round(pnl_r, 3),
                notes="; ".join(sig.notes),
            )
        )

    winners = [t for t in trades if t.pnl_r > 0]
    losers = [t for t in trades if t.pnl_r <= 0]
    total_r = sum(t.pnl_r for t in trades)
    return VenomBacktestResult(
        symbol=sym,
        interval=interval,
        period=period,
        days=len(days),
        trade_count=len(trades),
        winners=len(winners),
        losers=len(losers),
        win_rate=round(len(winners) / len(trades), 4) if trades else 0.0,
        total_r=round(total_r, 3),
        expectancy_r=round(total_r / len(trades), 3) if trades else 0.0,
        trades=trades,
        assumptions=[
            "Venom v1 mechanical: 08:00–09:30 ET box → post-09:30 sweep → FVG/BPR or engulf entry",
            f"Symbol={sym}; period={period}; interval={interval}; R={r_multiple}",
            "Underlying R multiples (not options premium)",
            "prepost=True when yfinance allows (box needs premarket)",
            f"Days with box={days_with_box}; days with signal={days_with_signal}",
            "Approximation of ICT Venom lecture — not discretionary ICT",
        ],
        metadata={
            "days_with_box": days_with_box,
            "days_with_signal": days_with_signal,
            "by_exit": {
                k: sum(1 for t in trades if t.exit_reason == k)
                for k in ("stop", "target", "time")
            },
            "by_side": {
                "CALL": sum(1 for t in trades if t.side == "CALL"),
                "PUT": sum(1 for t in trades if t.side == "PUT"),
            },
        },
    )


def run_venom_multi(
    symbols: Sequence[str] = ("QQQ", "SPY"),
    **kwargs,
) -> List[VenomBacktestResult]:
    return [run_venom_backtest(s, **kwargs) for s in symbols]


def render_venom_backtest(results: Sequence[VenomBacktestResult] | VenomBacktestResult) -> str:
    if isinstance(results, VenomBacktestResult):
        results = [results]
    lines = ["# Venom Model v1 Backtest", ""]
    for r in results:
        lines.extend(
            [
                f"## {r.symbol}",
                "",
                "### Assumptions",
            ]
        )
        for a in r.assumptions:
            lines.append(f"- {a}")
        lines.extend(
            [
                "",
                "### Results",
                f"- **Sessions scanned:** {r.days}",
                f"- **Trades:** {r.trade_count}",
                f"- **Winners / Losers:** {r.winners} / {r.losers}",
                f"- **Win rate:** **{r.win_rate * 100:.1f}%**",
                f"- **Total R:** {r.total_r:+.2f}R",
                f"- **Expectancy:** {r.expectancy_r:+.3f}R / trade",
                f"- **Exits:** {r.metadata.get('by_exit')}",
                f"- **Sides:** {r.metadata.get('by_side')}",
                "",
            ]
        )
        if r.trades:
            lines.append("### Sample trades (up to 12)")
            for t in r.trades[:12]:
                lines.append(
                    f"- {t.day} {t.side} {t.entry_type} @ {t.entry:.2f} → {t.exit:.2f} "
                    f"({t.exit_reason}) **{t.pnl_r:+.2f}R**"
                )
            lines.append("")
    lines.append(
        "_Research only — mechanical proxy of ICT Venom. Not financial advice._"
    )
    return "\n".join(lines)
