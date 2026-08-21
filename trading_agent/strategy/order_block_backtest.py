"""Historical backtest for ICT + SMC order-block entries (underlying R)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from trading_agent.pa.order_block import score_order_block_entry
from trading_agent.strategy.multi_method import fetch_bars

ET = ZoneInfo("America/New_York")
RTH_START = time(9, 35)
RTH_END = time(15, 55)


@dataclass
class ObTrade:
    symbol: str
    day: str
    side: str
    style_tag: str
    entry_time: str
    exit_time: str
    entry: float
    exit: float
    stop: float
    target: float
    exit_reason: str
    pnl_r: float
    score: float
    notes: str = ""


@dataclass
class ObBacktestResult:
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
    trades: List[ObTrade] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


def _bar_date(ts) -> date:
    try:
        if hasattr(ts, "tz_convert"):
            return ts.tz_convert(ET).date()
        if getattr(ts, "tzinfo", None) is not None:
            return ts.astimezone(ET).date()
        return ts.date()
    except Exception:
        return date.today()


def _bar_time(ts) -> time:
    try:
        if hasattr(ts, "tz_convert"):
            return ts.tz_convert(ET).time()
        if getattr(ts, "tzinfo", None) is not None:
            return ts.astimezone(ET).time()
        return ts.time()
    except Exception:
        return time(12, 0)


def _session_days(timestamps: Sequence) -> List[date]:
    return sorted({_bar_date(ts) for ts in timestamps})


def _simulate_exit(
    side: str,
    entry: float,
    stop: float,
    target: float,
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    times: Sequence,
) -> Tuple[float, str, Any]:
    for j in range(len(closes)):
        h, l = float(highs[j]), float(lows[j])
        if side == "CALL":
            # conservative: stop before target if both same bar
            if l <= stop:
                return stop, "stop", times[j]
            if h >= target:
                return target, "target", times[j]
        else:
            if h >= stop:
                return stop, "stop", times[j]
            if l <= target:
                return target, "target", times[j]
    return float(closes[-1]), "time", times[-1]


def _style_from_tags(tags: Sequence[str]) -> str:
    has_ict = any("ict" in t.lower() for t in tags)
    has_smc = any("smc" in t.lower() for t in tags)
    if has_ict and has_smc:
        return "ict+smc"
    if has_ict:
        return "ict"
    if has_smc:
        return "smc"
    if any("breaker" in t.lower() for t in tags):
        return "breaker"
    return "ob"


def run_order_block_backtest(
    symbol: str = "QQQ",
    *,
    period: str = "59d",
    interval: str = "15m",
    source: str = "yfinance",
    min_score: float = 55.0,
    styles: Sequence[str] = ("ict", "smc"),
    r_multiple: float = 1.5,
    max_trades_per_day: int = 2,
    hold_max_bars: int = 24,
    warmup_bars: int = 40,
    require_rejection: bool = True,
    df=None,
) -> ObBacktestResult:
    """Walk-forward OB mitigation entries; underlying R multiples (not options)."""
    sym = symbol.upper().strip()
    if df is None:
        df = fetch_bars(sym, period=period, interval=interval, source=source)

    df = df.copy()
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

    opens = (
        df["Open"].astype(float).tolist()
        if "Open" in df.columns
        else df["Close"].astype(float).tolist()
    )
    highs = df["High"].astype(float).tolist()
    lows = df["Low"].astype(float).tolist()
    closes = df["Close"].astype(float).tolist()
    times = list(df.index)
    n = len(closes)
    days = _session_days(times)

    trades: List[ObTrade] = []
    day_counts: Dict[date, int] = {}
    signals_seen = 0
    in_trade_until = -1

    for i in range(max(warmup_bars, 8), n):
        if i <= in_trade_until:
            continue
        d = _bar_date(times[i])
        t = _bar_time(times[i])
        if t < RTH_START or t > RTH_END:
            continue
        if day_counts.get(d, 0) >= max_trades_per_day:
            continue

        # no lookahead: only bars through i
        o = opens[: i + 1]
        h = highs[: i + 1]
        l = lows[: i + 1]
        c = closes[: i + 1]
        play, side, score, tags, entry, stop, target = score_order_block_entry(
            h,
            l,
            o,
            c,
            htf_direction="",
            styles=styles,
            require_rejection=require_rejection,
            r_multiple=r_multiple,
        )
        if not play or score < min_score or side not in ("CALL", "PUT"):
            continue
        if entry <= 0 or stop <= 0 or abs(entry - stop) < 1e-9:
            continue

        signals_seen += 1
        # path after entry bar
        end_j = min(n - 1, i + hold_max_bars)
        path_i = []
        for j in range(i + 1, end_j + 1):
            if _bar_date(times[j]) != d:
                break
            if _bar_time(times[j]) > RTH_END:
                break
            path_i.append(j)
        if not path_i:
            continue

        ph = [highs[j] for j in path_i]
        pl = [lows[j] for j in path_i]
        pc = [closes[j] for j in path_i]
        pt = [times[j] for j in path_i]
        exit_px, reason, exit_tm = _simulate_exit(side, entry, stop, target, ph, pl, pc, pt)
        risk = abs(entry - stop) or 1e-9
        if side == "CALL":
            pnl_r = (exit_px - entry) / risk
        else:
            pnl_r = (entry - exit_px) / risk

        style_tag = _style_from_tags(tags)
        trades.append(
            ObTrade(
                symbol=sym,
                day=d.isoformat(),
                side=side,
                style_tag=style_tag,
                entry_time=str(times[i]),
                exit_time=str(exit_tm),
                entry=round(entry, 4),
                exit=round(exit_px, 4),
                stop=round(stop, 4),
                target=round(target, 4),
                exit_reason=reason,
                pnl_r=round(pnl_r, 3),
                score=round(score, 1),
                notes="; ".join(tags[:8]),
            )
        )
        day_counts[d] = day_counts.get(d, 0) + 1
        # skip until exit bar index
        try:
            in_trade_until = path_i[pt.index(exit_tm)] if exit_tm in pt else path_i[-1]
        except Exception:
            in_trade_until = path_i[-1]

    winners = [t for t in trades if t.pnl_r > 0]
    losers = [t for t in trades if t.pnl_r <= 0]
    total_r = sum(t.pnl_r for t in trades)
    by_style: Dict[str, Dict[str, float]] = {}
    for t in trades:
        b = by_style.setdefault(t.style_tag, {"n": 0, "r": 0.0, "w": 0})
        b["n"] += 1
        b["r"] += t.pnl_r
        if t.pnl_r > 0:
            b["w"] += 1

    return ObBacktestResult(
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
            "Walk-forward: score_order_block_entry on bars[:i+1] only (no lookahead)",
            f"Styles={list(styles)}; min_score={min_score}; R={r_multiple}",
            f"Symbol={sym}; period={period}; interval={interval}",
            "Underlying R multiples (stop beyond zone, target = R×risk)",
            f"RTH entries {RTH_START.isoformat()}–{RTH_END.isoformat()} ET; "
            f"max {max_trades_per_day}/day; hold≤{hold_max_bars} bars",
            "Stop checked before target on same bar (conservative)",
            "HTF filter off in BT (isolated method edge)",
        ],
        metadata={
            "signals_seen": signals_seen,
            "by_exit": {
                k: sum(1 for t in trades if t.exit_reason == k)
                for k in ("stop", "target", "time")
            },
            "by_side": {
                "CALL": sum(1 for t in trades if t.side == "CALL"),
                "PUT": sum(1 for t in trades if t.side == "PUT"),
            },
            "by_style": {
                k: {
                    "trades": int(v["n"]),
                    "total_r": round(v["r"], 3),
                    "win_rate": round(v["w"] / v["n"], 3) if v["n"] else 0.0,
                }
                for k, v in by_style.items()
            },
        },
    )


def run_order_block_multi(
    symbols: Sequence[str] = ("QQQ", "SPY"),
    **kwargs,
) -> List[ObBacktestResult]:
    return [run_order_block_backtest(s, **kwargs) for s in symbols]


def run_order_block_style_split(
    symbol: str = "QQQ",
    **kwargs,
) -> Dict[str, ObBacktestResult]:
    """Separate BTs: ICT-only, SMC-only, both."""
    base = {k: v for k, v in kwargs.items() if k != "styles"}
    return {
        "ict": run_order_block_backtest(symbol, styles=("ict",), **base),
        "smc": run_order_block_backtest(symbol, styles=("smc",), **base),
        "both": run_order_block_backtest(symbol, styles=("ict", "smc"), **base),
    }


def render_order_block_backtest(
    results: Sequence[ObBacktestResult] | ObBacktestResult,
) -> str:
    if isinstance(results, ObBacktestResult):
        results = [results]
    lines = ["# Order Block Backtest (ICT + SMC)", ""]
    for r in results:
        lines.extend(["## " + r.symbol, "", "### Assumptions"])
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
                f"- **By style tag:** {r.metadata.get('by_style')}",
                "",
            ]
        )
        if r.trades:
            lines.append("### Sample trades (up to 12)")
            for t in r.trades[:12]:
                lines.append(
                    f"- {t.day} {t.side} [{t.style_tag}] score={t.score:.0f} "
                    f"@ {t.entry:.2f} → {t.exit:.2f} ({t.exit_reason}) **{t.pnl_r:+.2f}R**"
                )
            lines.append("")
    lines.append(
        "_Research only — mechanical OB proxy. Not financial advice._"
    )
    return "\n".join(lines)
