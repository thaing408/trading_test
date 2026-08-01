"""Opening Range Breakout + VWAP reclaim sleeve (prop-style intraday).

Industry staple: define OR from first N minutes; long break above ORH with
price above session VWAP; short break below ORL with price below VWAP.
Stop at OR mid or opposite rail; target 1R or 2R.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, time
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

ASSUMPTIONS = [
    "15m bars via yfinance; OR = first 30m (2 bars) 9:30–10:00 ET",
    "Long: close > OR high and close > session VWAP; short inverse",
    "Stop: OR midpoint; target: 1.5R; one trade per symbol per day",
    "Equity-style P/L in $ per share × 100 shares (not options premium)",
    "RTH only; no news filter",
]


@dataclass
class OrbTrade:
    symbol: str
    day: str
    side: str
    entry: float
    stop: float
    target: float
    exit: float
    exit_reason: str
    pnl: float
    r_multiple: float


@dataclass
class OrbBacktestResult:
    symbols: List[str]
    period: str
    trade_count: int
    winners: int
    losers: int
    win_rate: float
    total_pnl: float
    expectancy: float
    avg_r: float
    by_symbol: Dict[str, Dict[str, float]] = field(default_factory=dict)
    trades: List[OrbTrade] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


def _fetch(symbol: str, period: str = "60d"):
    import yfinance as yf

    df = yf.Ticker(symbol).history(period=period, interval="15m", auto_adjust=True)
    if df is None or df.empty:
        return None
    if getattr(df.index, "tz", None) is None:
        df = df.tz_localize(ET)
    else:
        df = df.tz_convert(ET)
    return df


def _session_date(ts) -> date:
    return ts.astimezone(ET).date() if getattr(ts, "tzinfo", None) else ts.date()


def run_orb_vwap_symbol(symbol: str, *, period: str = "60d", rr: float = 1.5) -> List[OrbTrade]:
    df = _fetch(symbol, period)
    if df is None or len(df) < 30:
        return []

    highs = df["High"].tolist()
    lows = df["Low"].tolist()
    closes = df["Close"].tolist()
    volumes = df["Volume"].tolist()
    times = list(df.index)

    by_day: Dict[date, List[int]] = defaultdict(list)
    for i, ts in enumerate(times):
        by_day[_session_date(ts)].append(i)

    trades: List[OrbTrade] = []
    for d, idxs in sorted(by_day.items()):
        # RTH bars
        rth = []
        for i in idxs:
            t = times[i].astimezone(ET).time()
            if time(9, 30) <= t <= time(15, 55):
                rth.append(i)
        if len(rth) < 6:
            continue

        # OR: first two 15m bars (30m)
        or_bars = rth[:2]
        orh = max(highs[i] for i in or_bars)
        orl = min(lows[i] for i in or_bars)
        mid = (orh + orl) / 2.0
        if orh - orl < 1e-6:
            continue

        # session cumulative for VWAP
        cum_pv = 0.0
        cum_v = 0.0
        traded = False
        for j, i in enumerate(rth):
            c = float(closes[i])
            h = float(highs[i])
            l = float(lows[i])
            v = float(volumes[i] or 0)
            # update VWAP with this bar (typical price)
            tp = (h + l + c) / 3.0
            cum_pv += tp * max(v, 1.0)
            cum_v += max(v, 1.0)
            vwap = cum_pv / cum_v

            if j < 2 or traded:
                continue
            # after OR complete
            side = None
            if c > orh and c > vwap:
                side = "long"
                entry = c
                stop = mid
                risk = entry - stop
                if risk <= 0:
                    continue
                target = entry + rr * risk
            elif c < orl and c < vwap:
                side = "short"
                entry = c
                stop = mid
                risk = stop - entry
                if risk <= 0:
                    continue
                target = entry - rr * risk
            else:
                continue

            # simulate forward in session
            fut = rth[j + 1 :]
            exit_px = float(closes[fut[-1]]) if fut else entry
            reason = "time_exit"
            for k in fut:
                hh, ll, cc = float(highs[k]), float(lows[k]), float(closes[k])
                if side == "long":
                    if ll <= stop:
                        exit_px, reason = stop, "stop"
                        break
                    if hh >= target:
                        exit_px, reason = target, "target"
                        break
                else:
                    if hh >= stop:
                        exit_px, reason = stop, "stop"
                        break
                    if ll <= target:
                        exit_px, reason = target, "target"
                        break
                exit_px = cc

            if side == "long":
                pnl_ps = exit_px - entry
            else:
                pnl_ps = entry - exit_px
            r_mult = pnl_ps / risk if risk else 0.0
            pnl = pnl_ps * 100  # 100 shares
            trades.append(
                OrbTrade(
                    symbol=symbol.upper(),
                    day=d.isoformat(),
                    side=side,
                    entry=round(entry, 4),
                    stop=round(stop, 4),
                    target=round(target, 4),
                    exit=round(exit_px, 4),
                    exit_reason=reason,
                    pnl=round(pnl, 2),
                    r_multiple=round(r_mult, 3),
                )
            )
            traded = True
    return trades


def run_orb_vwap_backtest(
    symbols: Optional[Sequence[str]] = None,
    *,
    period: str = "60d",
    rr: float = 1.5,
) -> OrbBacktestResult:
    syms = [s.upper() for s in (symbols or ["QQQ", "SPY", "IWM"])]
    all_t: List[OrbTrade] = []
    by_sym: Dict[str, Dict[str, float]] = {}
    for s in syms:
        try:
            ts = run_orb_vwap_symbol(s, period=period, rr=rr)
        except Exception:
            ts = []
        all_t.extend(ts)
        wins = sum(1 for t in ts if t.pnl > 0)
        total = sum(t.pnl for t in ts)
        by_sym[s] = {
            "n": float(len(ts)),
            "wr": wins / len(ts) if ts else 0.0,
            "pnl": round(total, 2),
            "exp": round(total / len(ts), 2) if ts else 0.0,
            "avg_r": round(sum(t.r_multiple for t in ts) / len(ts), 3) if ts else 0.0,
        }
    wins = [t for t in all_t if t.pnl > 0]
    losses = [t for t in all_t if t.pnl <= 0]
    total = sum(t.pnl for t in all_t)
    return OrbBacktestResult(
        symbols=syms,
        period=period,
        trade_count=len(all_t),
        winners=len(wins),
        losers=len(losses),
        win_rate=len(wins) / len(all_t) if all_t else 0.0,
        total_pnl=round(total, 2),
        expectancy=round(total / len(all_t), 2) if all_t else 0.0,
        avg_r=round(sum(t.r_multiple for t in all_t) / len(all_t), 3) if all_t else 0.0,
        by_symbol=by_sym,
        trades=all_t,
        assumptions=list(ASSUMPTIONS),
    )


def format_orb_report(r: OrbBacktestResult) -> str:
    lines = [
        f"# ORB + VWAP sleeve ({r.period})",
        "",
        "## Assumptions",
    ]
    for a in r.assumptions:
        lines.append(f"- {a}")
    lines += [
        "",
        f"**Trades:** {r.trade_count}  **WR:** {r.win_rate:.1%}  "
        f"**Exp:** ${r.expectancy:+.2f}  **Total:** ${r.total_pnl:+.2f}  **Avg R:** {r.avg_r:+.2f}",
        "",
        "| Symbol | n | WR | Exp | P/L | Avg R |",
        "|--------|---|-----|-----|-----|-------|",
    ]
    for s, b in r.by_symbol.items():
        lines.append(
            f"| {s} | {int(b['n'])} | {b['wr']:.0%} | ${b['exp']:+.2f} | "
            f"${b['pnl']:+.2f} | {b['avg_r']:+.2f} |"
        )
    return "\n".join(lines) + "\n"
