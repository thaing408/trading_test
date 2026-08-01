"""Multi-ticker backtest of schwab-mcp QQQ scalper rules.

Uses pure logic from ``schwab_mcp.qqq_strategy`` when importable; otherwise a
local minimal reimplementation of entry levels + stop/target exits.

Assumptions (labeled in reports):
- Levels rebuilt each session from **prior close** via ``levels_from_spot``
  (percent bands) so history is not stuck on one day's fixed TV levels.
- Intraday path: 15m (ETFs) or 60m (single names) bars from yfinance.
- Option P/L: synthetic premium $1.00; ±profit_pct / −loss_pct on premium
  (default +25% / −30% matching live scalp config), OR underlying stop/target
  first (whichever hits first in bar path using high/low).
- One position at a time per symbol; max_round_trips / max_losing per day enforced.
- No IV/VIX gate in offline path (optional static VIX).
"""

from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
PT = ZoneInfo("America/Los_Angeles")

ASSUMPTIONS = [
    "Levels each day from prior close via levels_from_spot (% bands), not fixed TV pins",
    "Bars: yfinance 15m (ETFs) or 60m (stocks); period limited by Yahoo intraday",
    "Synthetic option $1 entry; hard PT +25% / SL −30% on premium OR underlying stop/target",
    "Delta≈0.45 for premium move from underlying; first of stop/target/premium wins",
    "One open scalp per symbol; daily max_round_trips / max_losing / max_winning",
    "No live IV richness / VIX filter in offline run (unless vix= passed)",
]


def _import_qqq_strategy():
    """Load pure ``qqq_strategy.py`` by file path (avoid schwab_mcp package deps)."""
    import importlib.util

    candidates = [
        Path.home() / "schwab-mcp-server" / "src" / "schwab_mcp" / "qqq_strategy.py",
        Path("/Users/thai/schwab-mcp-server/src/schwab_mcp/qqq_strategy.py"),
    ]
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        raise ImportError(
            "qqq_strategy.py not found under ~/schwab-mcp-server — install sibling repo"
        )
    spec = importlib.util.spec_from_file_location("qqq_strategy_standalone", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    # Isolate name so package __init__ is not pulled in
    sys.modules["qqq_strategy_standalone"] = mod
    spec.loader.exec_module(mod)
    return {
        "ActionType": mod.ActionType,
        "DailyState": mod.DailyState,
        "SetupType": mod.SetupType,
        "evaluate_entry": mod.evaluate_entry,
        "levels_from_spot": mod.levels_from_spot,
        "get_symbol_levels": mod.get_symbol_levels,
        "ScalpLevels": mod.ScalpLevels,
        "scale_levels": mod.scale_levels,
    }


@dataclass
class ScalpTrade:
    symbol: str
    day: str
    setup: str
    side: str  # CALL | PUT
    entry_time: str
    exit_time: str
    entry_spot: float
    exit_spot: float
    exit_reason: str
    pnl_pct: float
    pnl_dollars: float
    bars_held: int


@dataclass
class SymbolScalpStats:
    symbol: str
    trade_count: int = 0
    winners: int = 0
    losers: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    expectancy: float = 0.0
    by_setup: Dict[str, Dict[str, float]] = field(default_factory=dict)


@dataclass
class ScalpBacktestResult:
    symbols: List[str]
    period: str
    trade_count: int
    winners: int
    losers: int
    win_rate: float
    total_pnl: float
    expectancy: float
    by_symbol: Dict[str, SymbolScalpStats] = field(default_factory=dict)
    by_setup: Dict[str, Dict[str, float]] = field(default_factory=dict)
    trades: List[ScalpTrade] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


def _fetch_intraday(symbol: str, interval: str, period: str):
    import yfinance as yf

    df = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=True)
    if df is None or df.empty:
        return None
    if getattr(df.index, "tz", None) is None:
        df = df.tz_localize(ET)
    else:
        df = df.tz_convert(ET)
    return df


def _session_date(ts) -> date:
    # US RTH date in ET
    if hasattr(ts, "date"):
        return ts.astimezone(ET).date() if getattr(ts, "tzinfo", None) else ts.date()
    return date.today()


def _simulate_exit(
    *,
    is_long: bool,
    entry_spot: float,
    stop: float,
    target: float,
    future_highs: Sequence[float],
    future_lows: Sequence[float],
    future_closes: Sequence[float],
    profit_pct: float = 25.0,
    loss_pct: float = 30.0,
    delta: float = 0.45,
    entry_prem: float = 1.0,
) -> Tuple[float, str, int, float]:
    """Return (exit_spot, reason, bars_held, pnl_pct on premium)."""
    for i, (h, l, c) in enumerate(zip(future_highs, future_lows, future_closes)):
        # Underlying structural
        if is_long:
            if l <= stop:
                # premium loss from move
                d_und = stop - entry_spot
                d_prem = delta * d_und
                exit_prem = max(0.01, entry_prem + d_prem)
                pnl_pct = (exit_prem - entry_prem) / entry_prem * 100
                # hard floor at -loss_pct
                pnl_pct = max(pnl_pct, -loss_pct)
                return stop, "underlying_stop", i + 1, pnl_pct
            if h >= target:
                d_und = target - entry_spot
                d_prem = delta * d_und
                exit_prem = entry_prem + d_prem
                pnl_pct = (exit_prem - entry_prem) / entry_prem * 100
                pnl_pct = min(pnl_pct, profit_pct) if pnl_pct > 0 else pnl_pct
                # if structural target but premium model already hit PT
                if pnl_pct >= profit_pct:
                    return target, "premium_target", i + 1, profit_pct
                return target, "underlying_target", i + 1, pnl_pct
        else:
            if h >= stop:
                d_und = entry_spot - stop  # adverse for put
                d_prem = -delta * (stop - entry_spot)  # put gains when down
                # put: when price goes up to stop, put loses
                d_prem = delta * (entry_spot - stop)  # negative when stop > entry
                # stop > entry for short-underlying (put long): adverse is up
                d_prem = -delta * (stop - entry_spot)
                exit_prem = max(0.01, entry_prem + d_prem)
                pnl_pct = (exit_prem - entry_prem) / entry_prem * 100
                pnl_pct = max(pnl_pct, -loss_pct)
                return stop, "underlying_stop", i + 1, pnl_pct
            if l <= target:
                d_prem = delta * (entry_spot - target)  # put profits
                exit_prem = entry_prem + d_prem
                pnl_pct = (exit_prem - entry_prem) / entry_prem * 100
                if pnl_pct >= profit_pct:
                    return target, "premium_target", i + 1, profit_pct
                return target, "underlying_target", i + 1, pnl_pct

        # Premium path along bar close
        if is_long:
            d_prem = delta * (c - entry_spot)
        else:
            d_prem = delta * (entry_spot - c)
        exit_prem = max(0.01, entry_prem + d_prem)
        pnl_pct = (exit_prem - entry_prem) / entry_prem * 100
        if pnl_pct <= -loss_pct:
            return float(c), "premium_stop", i + 1, -loss_pct
        if pnl_pct >= profit_pct:
            return float(c), "premium_target", i + 1, profit_pct

    # time exit at last close
    c = float(future_closes[-1]) if future_closes else entry_spot
    if is_long:
        d_prem = delta * (c - entry_spot)
    else:
        d_prem = delta * (entry_spot - c)
    exit_prem = max(0.01, entry_prem + d_prem)
    pnl_pct = (exit_prem - entry_prem) / entry_prem * 100
    pnl_pct = max(-loss_pct, min(profit_pct, pnl_pct))
    return c, "time_exit", len(future_closes), pnl_pct


def run_symbol_scalp_backtest(
    symbol: str,
    *,
    period: str = "60d",
    vix: Optional[float] = None,
    max_hold_bars: int = 12,
    allow_bear_breakdown: bool = True,
    last_n_sessions: Optional[int] = None,
) -> Tuple[List[ScalpTrade], Dict[str, Any]]:
    qs = _import_qqq_strategy()
    evaluate_entry = qs["evaluate_entry"]
    levels_from_spot = qs["levels_from_spot"]
    DailyState = qs["DailyState"]
    ActionType = qs["ActionType"]
    SetupType = qs["SetupType"]

    is_etf = symbol.upper() in {"QQQ", "SPY", "IWM", "DIA", "TQQQ", "SQQQ"}
    interval = "15m" if is_etf else "60m"
    # yfinance intraday: 15m max 60d, 60m max 60d-ish
    df = _fetch_intraday(symbol, interval, period)
    if df is None or len(df) < 20:
        return [], {"error": "no_bars", "symbol": symbol, "interval": interval}

    highs = df["High"].tolist()
    lows = df["Low"].tolist()
    closes = df["Close"].tolist()
    times = list(df.index)

    # prior close by session
    by_day: Dict[date, List[int]] = defaultdict(list)
    for i, ts in enumerate(times):
        by_day[_session_date(ts)].append(i)

    days_sorted = sorted(by_day.keys())
    prior_close: Dict[date, float] = {}
    for d in days_sorted:
        idxs = by_day[d]
        prior_close[d] = float(closes[idxs[-1]])

    # Optional: only last N sessions (need +1 prior day for levels)
    if last_n_sessions is not None and last_n_sessions > 0 and len(days_sorted) > last_n_sessions + 1:
        days_sorted = days_sorted[-(last_n_sessions + 1) :]

    trades: List[ScalpTrade] = []
    for di, d in enumerate(days_sorted):
        if di == 0:
            continue  # need prior close
        prev = days_sorted[di - 1]
        spot0 = prior_close.get(prev)
        if spot0 is None:
            # prior close may be outside truncated window — use first bar open of day
            spot0 = float(closes[by_day[d][0]])
        levels = levels_from_spot(symbol, spot0)
        state = DailyState(session_date=d.isoformat())
        idxs = by_day[d]
        session_closes: List[float] = []
        j = 0
        while j < len(idxs):
            i = idxs[j]
            # RTH only 9:30–16:00 ET
            ts = times[i]
            t = ts.astimezone(ET).time() if hasattr(ts, "astimezone") else time(12, 0)
            if t < time(9, 30) or t > time(16, 0):
                j += 1
                continue
            px = float(closes[i])
            session_closes.append(px)

            if state.halted or (
                state.round_trips >= levels.max_round_trips
                or state.losing_scalps >= levels.max_losing_scalps
                or state.winning_scalps >= levels.max_winning_scalps
            ):
                j += 1
                continue

            if state.open_setup:
                j += 1
                continue

            sig = evaluate_entry(px, session_closes, levels, state=state, vix=vix)
            if sig.action != ActionType.ENTER:
                j += 1
                continue

            setup = sig.setup
            if not allow_bear_breakdown and setup == SetupType.BEAR_BREAKDOWN:
                j += 1
                continue

            is_long = setup in {SetupType.BULL_BREAKOUT, SetupType.PULLBACK_LONG}
            stop = float(sig.stop_underlying or 0)
            target = float(sig.target_underlying or 0)
            if stop <= 0 or target <= 0:
                j += 1
                continue

            # forward path within session
            fut_idx = idxs[j + 1 : j + 1 + max_hold_bars]
            if not fut_idx:
                j += 1
                continue
            fh = [float(highs[k]) for k in fut_idx]
            fl = [float(lows[k]) for k in fut_idx]
            fc = [float(closes[k]) for k in fut_idx]
            exit_spot, reason, held, pnl_pct = _simulate_exit(
                is_long=is_long,
                entry_spot=px,
                stop=stop,
                target=target,
                future_highs=fh,
                future_lows=fl,
                future_closes=fc,
                profit_pct=levels.profit_pct,
                loss_pct=levels.loss_pct,
            )
            pnl_dollars = 1.0 * 100 * (pnl_pct / 100.0)  # $1 premium × 100
            side = "CALL" if is_long else "PUT"
            exit_ts = times[fut_idx[held - 1]] if held <= len(fut_idx) else times[fut_idx[-1]]
            trades.append(
                ScalpTrade(
                    symbol=symbol.upper(),
                    day=d.isoformat(),
                    setup=setup.value if hasattr(setup, "value") else str(setup),
                    side=side,
                    entry_time=str(ts),
                    exit_time=str(exit_ts),
                    entry_spot=px,
                    exit_spot=exit_spot,
                    exit_reason=reason,
                    pnl_pct=round(pnl_pct, 2),
                    pnl_dollars=round(pnl_dollars, 2),
                    bars_held=held,
                )
            )
            state.round_trips += 1
            if pnl_pct > 0:
                state.winning_scalps += 1
            elif pnl_pct < 0:
                state.losing_scalps += 1
            # skip held bars
            j += held + 1

    meta = {
        "symbol": symbol,
        "interval": interval,
        "bars": len(closes),
        "sessions": len(days_sorted),
        "n_trades": len(trades),
        "allow_bear_breakdown": allow_bear_breakdown,
        "last_n_sessions": last_n_sessions,
    }
    return trades, meta


def _stats(trades: List[ScalpTrade], symbol: str) -> SymbolScalpStats:
    if not trades:
        return SymbolScalpStats(symbol=symbol)
    wins = [t for t in trades if t.pnl_dollars > 0]
    losses = [t for t in trades if t.pnl_dollars <= 0]
    by_setup: Dict[str, Dict[str, float]] = {}
    for t in trades:
        b = by_setup.setdefault(t.setup, {"n": 0, "wins": 0, "pnl": 0.0})
        b["n"] += 1
        b["pnl"] += t.pnl_dollars
        if t.pnl_dollars > 0:
            b["wins"] += 1
    for s, b in by_setup.items():
        b["win_rate"] = b["wins"] / b["n"] if b["n"] else 0.0
    total = sum(t.pnl_dollars for t in trades)
    return SymbolScalpStats(
        symbol=symbol,
        trade_count=len(trades),
        winners=len(wins),
        losers=len(losses),
        win_rate=len(wins) / len(trades) if trades else 0.0,
        total_pnl=round(total, 2),
        expectancy=round(total / len(trades), 2) if trades else 0.0,
        by_setup=by_setup,
    )


DEFAULT_SCALP_SYMBOLS = ("QQQ", "SPY", "IWM", "AAPL", "AMZN", "MSFT", "NVDA", "META", "TSLA")
ETF_SCALP_SYMBOLS = ("QQQ", "SPY", "IWM")


def run_multi_symbol_scalp_backtest(
    symbols: Optional[Sequence[str]] = None,
    *,
    period: str = "60d",
    vix: Optional[float] = None,
    allow_bear_breakdown: bool = True,
    last_n_sessions: Optional[int] = None,
    etfs_only: bool = False,
) -> ScalpBacktestResult:
    if etfs_only:
        syms = [s.upper() for s in ETF_SCALP_SYMBOLS]
    else:
        syms = [s.upper() for s in (symbols or DEFAULT_SCALP_SYMBOLS)]
    all_trades: List[ScalpTrade] = []
    by_symbol: Dict[str, SymbolScalpStats] = {}
    meta_sym: Dict[str, Any] = {}

    for sym in syms:
        try:
            trades, meta = run_symbol_scalp_backtest(
                sym,
                period=period,
                vix=vix,
                allow_bear_breakdown=allow_bear_breakdown,
                last_n_sessions=last_n_sessions,
            )
        except Exception as exc:
            trades, meta = [], {"error": str(exc), "symbol": sym}
        meta_sym[sym] = meta
        by_symbol[sym] = _stats(trades, sym)
        all_trades.extend(trades)

    wins = [t for t in all_trades if t.pnl_dollars > 0]
    losses = [t for t in all_trades if t.pnl_dollars <= 0]
    total = sum(t.pnl_dollars for t in all_trades)
    by_setup: Dict[str, Dict[str, float]] = {}
    for t in all_trades:
        b = by_setup.setdefault(t.setup, {"n": 0, "wins": 0, "pnl": 0.0})
        b["n"] += 1
        b["pnl"] += t.pnl_dollars
        if t.pnl_dollars > 0:
            b["wins"] += 1
    for s, b in by_setup.items():
        b["win_rate"] = round(b["wins"] / b["n"], 4) if b["n"] else 0.0
        b["pnl"] = round(b["pnl"], 2)

    label = period
    if last_n_sessions:
        label = f"{period}_last{last_n_sessions}sess"
    if not allow_bear_breakdown:
        label += "_no_bear"
    if etfs_only:
        label += "_etf"

    assumptions = list(ASSUMPTIONS)
    if not allow_bear_breakdown:
        assumptions.append("bear_breakdown entries DISABLED")
    if etfs_only:
        assumptions.append("Universe: ETFs only (QQQ, SPY, IWM)")
    if last_n_sessions:
        assumptions.append(f"Only last {last_n_sessions} RTH sessions scored")

    return ScalpBacktestResult(
        symbols=syms,
        period=label,
        trade_count=len(all_trades),
        winners=len(wins),
        losers=len(losses),
        win_rate=len(wins) / len(all_trades) if all_trades else 0.0,
        total_pnl=round(total, 2),
        expectancy=round(total / len(all_trades), 2) if all_trades else 0.0,
        by_symbol=by_symbol,
        by_setup=by_setup,
        trades=all_trades,
        assumptions=assumptions,
        metadata={
            "per_symbol": meta_sym,
            "allow_bear_breakdown": allow_bear_breakdown,
            "last_n_sessions": last_n_sessions,
            "etfs_only": etfs_only,
            "fetch_period": period,
        },
    )


def format_scalp_backtest_report(result: ScalpBacktestResult) -> str:
    lines = [
        f"# QQQ-style scalp multi-ticker backtest ({result.period})",
        "",
        "## Assumptions",
    ]
    for a in result.assumptions:
        lines.append(f"- {a}")
    lines += [
        "",
        "## Aggregate",
        f"- **Trades:** {result.trade_count}",
        f"- **Win rate:** {result.win_rate:.1%} ({result.winners}W / {result.losers}L)",
        f"- **Total P/L:** ${result.total_pnl:+,.2f} (synthetic $1 premium)",
        f"- **Expectancy:** ${result.expectancy:+.2f} / trade",
        f"- **Symbols:** {', '.join(result.symbols)}",
        "",
        "## Win rate by symbol",
        "",
        "| Symbol | Trades | WR | W/L | Expectancy | Total P/L |",
        "|--------|--------|-----|-----|------------|-----------|",
    ]
    # sort by win rate then n
    rows = sorted(
        result.by_symbol.values(),
        key=lambda s: (-s.win_rate, -s.trade_count),
    )
    for s in rows:
        lines.append(
            f"| {s.symbol} | {s.trade_count} | {s.win_rate:.0%} | "
            f"{s.winners}/{s.losers} | ${s.expectancy:+.2f} | ${s.total_pnl:+.2f} |"
        )
    lines += [
        "",
        "## By setup (all symbols)",
        "",
        "| Setup | n | WR | P/L |",
        "|-------|---|-----|-----|",
    ]
    for setup, b in sorted(result.by_setup.items(), key=lambda x: -x[1].get("n", 0)):
        lines.append(
            f"| {setup} | {int(b['n'])} | {b.get('win_rate', 0):.0%} | ${b.get('pnl', 0):+.2f} |"
        )
    lines += ["", "## Sample trades (first 25)", ""]
    for t in result.trades[:25]:
        lines.append(
            f"- {t.day} {t.symbol} {t.setup} {t.side} "
            f"{t.exit_reason} pnl={t.pnl_pct:+.1f}% (${t.pnl_dollars:+.2f})"
        )
    if not result.trades:
        lines.append("- _No trades._")
        # show errors
        for sym, m in (result.metadata.get("per_symbol") or {}).items():
            if m.get("error"):
                lines.append(f"- {sym}: {m.get('error')}")
    return "\n".join(lines) + "\n"
