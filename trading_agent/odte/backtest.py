"""Backtest Shen-style 0DTE level+RSI playbook on QQQ (or SPY) 1-minute data.

Assumptions (labeled in reports):
- Synthetic option premium starts at $1.00; dPremium ≈ delta × dUnderlying ($).
- Bracket: +take_profit_pct / −stop_loss_pct on that premium (default +15% / −18%).
- Structural levels (PD/PM/OR) by default; whole-dollar rails optional via config.
- One position at a time; first-touch per level per day; entries only in ET window.
- Not full options-chain pricing (no IV surface) — success rate is relative to this model.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

import numpy as np

from trading_agent.odte.playbook import (
    OdtePlaybookConfig,
    level_allowed_for_entry,
    rejection_close_ok,
    rsi_series,
    signal_side_for_touch,
    whole_dollar_levels,
)

ET = ZoneInfo("America/New_York")


@dataclass
class OdteTrade:
    day: str
    side: str  # CALL | PUT
    level_name: str
    level: float
    entry_time: str
    exit_time: str
    entry_spot: float
    exit_spot: float
    entry_prem: float
    exit_prem: float
    exit_reason: str
    pnl_pct: float
    pnl_dollars: float
    rsi_at_entry: float


@dataclass
class OdteBacktestResult:
    symbol: str
    days: int
    trade_count: int
    winners: int
    losers: int
    win_rate: float
    total_pnl: float
    expectancy: float
    profit_factor: float
    max_drawdown: float
    avg_pnl_pct: float
    by_side: Dict[str, Dict[str, float]] = field(default_factory=dict)
    by_exit: Dict[str, int] = field(default_factory=dict)
    trades: List[OdteTrade] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


def _to_et_index(df):
    idx = df.index
    if getattr(idx, "tz", None) is None:
        return idx.tz_localize(ET)
    return idx.tz_convert(ET)


def fetch_qqq_1m(
    symbol: str = "QQQ",
    period: str = "7d",
    *,
    source: str = "auto",
):
    """Load 1m OHLCV for ODTE backtest.

    source:
      - auto: Schwab/TOS when token available, else yfinance
      - schwab | tos: Schwab Market Data API (same feed as thinkorswim)
      - yfinance | yf: Yahoo Finance
    """
    src = (source or "auto").strip().lower()
    if src in ("auto", "schwab", "tos"):
        try:
            from trading_agent.market_data.schwab_ohlcv import (
                fetch_schwab_ohlcv_dataframe,
                schwab_available,
            )

            if src in ("schwab", "tos") or schwab_available():
                # Schwab minute history: periodType=day allows 1–5 or 10 (not 6–9)
                schwab_period = period
                if period.endswith("d") and period[:-1].isdigit():
                    n = int(period[:-1])
                    n = max(1, min(n, 10))
                    if 6 <= n <= 9:
                        n = 10
                    schwab_period = f"{n}d"
                else:
                    schwab_period = "10d"
                df = fetch_schwab_ohlcv_dataframe(
                    symbol, interval="1m", period=schwab_period, extended_hours=True
                )
                if df is not None and not df.empty:
                    df = df.copy()
                    df.index = _to_et_index(df)
                    df.attrs["data_source"] = "schwab"
                    return df
                if src in ("schwab", "tos"):
                    raise ValueError(f"No Schwab 1m history for {symbol}")
        except Exception:
            if src in ("schwab", "tos"):
                raise
            # auto → fall through to yfinance

    import yfinance as yf

    t = yf.Ticker(symbol)
    df = t.history(period=period, interval="1m", auto_adjust=True)
    if df is None or df.empty:
        raise ValueError(f"No 1m history for {symbol}")
    df = df.copy()
    df.index = _to_et_index(df)
    df.attrs["data_source"] = "yfinance"
    return df


def _session_days(df) -> List[date]:
    days = sorted({ts.date() for ts in df.index})
    return days


def _day_slice(df, d: date):
    mask = [ts.date() == d for ts in df.index]
    return df.loc[mask]


def _prior_day_hl(df, d: date) -> Tuple[Optional[float], Optional[float]]:
    days = _session_days(df)
    if d not in days:
        return None, None
    i = days.index(d)
    if i == 0:
        return None, None
    prev = _day_slice(df, days[i - 1])
    if prev.empty:
        return None, None
    return float(prev["High"].max()), float(prev["Low"].min())


def _opening_range(day_df, or_minutes: int = 5) -> Tuple[Optional[float], Optional[float]]:
    rth = day_df.between_time(time(9, 30), time(16, 0))
    if rth.empty:
        return None, None
    # first or_minutes bars
    head = rth.iloc[: max(or_minutes, 1)]
    return float(head["High"].max()), float(head["Low"].min())


def _premarket_hl(day_df) -> Tuple[Optional[float], Optional[float]]:
    pre = day_df.between_time(time(4, 0), time(9, 29))
    if pre.empty:
        return None, None
    return float(pre["High"].max()), float(pre["Low"].min())


def _in_window(ts: datetime, start: time, end: time) -> bool:
    t = ts.timetz().replace(tzinfo=None) if False else ts.time()
    return start <= t <= end


def _simulate_premium_path(
    side: str,
    entry_spot: float,
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    times: Sequence[Any],
    *,
    entry_prem: float,
    tp_prem: float,
    sl_prem: float,
    delta: float,
) -> Tuple[float, float, str, Any]:
    """Walk bars after entry; return exit_prem, exit_spot, reason, exit_time."""
    for h, l, c, tm in zip(highs, lows, closes, times):
        if side == "CALL":
            # Best premium path uses favorable extreme first (conservative: check SL on low, TP on high)
            prem_hi = entry_prem + delta * (h - entry_spot)
            prem_lo = entry_prem + delta * (l - entry_spot)
            if prem_lo <= sl_prem:
                return sl_prem, l, "stop_loss", tm
            if prem_hi >= tp_prem:
                return tp_prem, h, "take_profit", tm
            prem_c = entry_prem + delta * (c - entry_spot)
        else:
            prem_hi = entry_prem + delta * (entry_spot - l)  # put benefits from low
            prem_lo = entry_prem + delta * (entry_spot - h)
            if prem_lo <= sl_prem:
                return sl_prem, h, "stop_loss", tm
            if prem_hi >= tp_prem:
                return tp_prem, l, "take_profit", tm
            prem_c = entry_prem + delta * (entry_spot - c)
        # continue
    # time stop at last bar
    c = closes[-1] if closes else entry_spot
    tm = times[-1] if times else None
    if side == "CALL":
        prem = entry_prem + delta * (c - entry_spot)
    else:
        prem = entry_prem + delta * (entry_spot - c)
    return max(prem, 0.01), c, "time_exit", tm


def run_odte_backtest(
    symbol: str = "QQQ",
    *,
    period: str = "7d",
    cfg: OdtePlaybookConfig | None = None,
    delta: float = 0.55,
    entry_prem: float = 1.0,
    contracts: int = 2,
    max_trades_per_day: int = 3,
    df=None,
    data_source: str = "auto",
) -> OdteBacktestResult:
    """Backtest playbook on 1m bars.

    contracts: number of contracts (×100 multiplier for $ P/L from premium).
    delta: $ premium change per $1 underlying (synthetic 0DTE leverage).
    data_source: auto | schwab | tos | yfinance (used when df is None).
    """
    cfg = cfg or OdtePlaybookConfig(symbol=symbol)
    cfg.symbol = symbol
    if df is None:
        df = fetch_qqq_1m(symbol, period=period, source=data_source)

    closes_all = df["Close"].astype(float).tolist()
    rsi_all = rsi_series(closes_all, cfg.rsi_length)
    df = df.copy()
    df["rsi"] = rsi_all

    trades: List[OdteTrade] = []
    equity = cfg.account_size
    curve = [equity]
    days = _session_days(df)

    for d in days:
        day_df = _day_slice(df, d)
        rth = day_df.between_time(cfg.window_start_et, time(16, 0))
        if len(rth) < cfg.rsi_length + 5:
            continue
        pdh, pdl = _prior_day_hl(df, d)
        if pdh is None:
            continue
        orh, orl = _opening_range(day_df, cfg.or_minutes)
        pmh, pml = _premarket_hl(day_df)

        # levels that can trigger
        touched: set[float] = set()  # first-touch tracker by rounded level
        open_trade: Optional[dict] = None
        day_trades = 0

        bars = rth.between_time(cfg.window_start_et, cfg.window_end_et)
        if bars.empty:
            continue

        times = list(bars.index)
        for i, ts in enumerate(times):
            row = bars.iloc[i]
            price = float(row["Close"])
            hi = float(row["High"])
            lo = float(row["Low"])
            rsi = float(row["rsi"])

            # manage open trade
            if open_trade is not None:
                # collect path from entry index
                j0 = open_trade["i"]
                if i <= j0:
                    continue
                sub = bars.iloc[j0 + 1 : i + 1]
                ep, es, reason, etm = _simulate_premium_path(
                    open_trade["side"],
                    open_trade["entry_spot"],
                    sub["High"].astype(float).tolist(),
                    sub["Low"].astype(float).tolist(),
                    sub["Close"].astype(float).tolist(),
                    list(sub.index),
                    entry_prem=entry_prem,
                    tp_prem=entry_prem * (1 + cfg.take_profit_pct),
                    sl_prem=entry_prem * (1 - cfg.stop_loss_pct),
                    delta=delta,
                )
                # Only close if TP/SL hit on this bar or last bar of window
                hit = reason in ("take_profit", "stop_loss")
                end_window = i == len(times) - 1
                if hit or end_window:
                    if not hit and end_window:
                        # recompute mark at close of this bar
                        if open_trade["side"] == "CALL":
                            ep = entry_prem + delta * (price - open_trade["entry_spot"])
                        else:
                            ep = entry_prem + delta * (open_trade["entry_spot"] - price)
                        ep = max(ep, 0.01)
                        es = price
                        reason = "time_exit"
                        etm = ts
                    pnl_pct = (ep - entry_prem) / entry_prem
                    # $ P/L: premium $ × 100 × contracts
                    risk_dollars = entry_prem * 100 * contracts
                    pnl_dollars = (ep - entry_prem) * 100 * contracts
                    trades.append(
                        OdteTrade(
                            day=d.isoformat(),
                            side=open_trade["side"],
                            level_name=open_trade["level_name"],
                            level=open_trade["level"],
                            entry_time=str(open_trade["entry_time"]),
                            exit_time=str(etm),
                            entry_spot=open_trade["entry_spot"],
                            exit_spot=float(es),
                            entry_prem=entry_prem,
                            exit_prem=float(ep),
                            exit_reason=reason if hit else "time_exit",
                            pnl_pct=round(pnl_pct, 4),
                            pnl_dollars=round(pnl_dollars, 2),
                            rsi_at_entry=open_trade["rsi"],
                        )
                    )
                    equity += pnl_dollars
                    curve.append(equity)
                    open_trade = None
                    if hit:
                        continue  # can look for new entry same bar after exit — skip for simplicity
                else:
                    continue

            if day_trades >= max_trades_per_day:
                continue
            if not _in_window(ts.to_pydatetime(), cfg.window_start_et, cfg.window_end_et):
                continue

            candidates: List[Tuple[str, float, str]] = []
            if cfg.use_whole_dollar_levels:
                above, below = whole_dollar_levels(price, n=6)
                for x in above:
                    candidates.append((f"whole ${x:.0f}", x, "resistance"))
                for x in below:
                    candidates.append((f"whole ${x:.0f}", x, "support"))
            candidates.append(("PDH", pdh, "resistance"))
            candidates.append(("PDL", pdl, "support"))
            if orh is not None:
                candidates.append(("ORH", orh, "resistance"))
            if orl is not None:
                candidates.append(("ORL", orl, "support"))
            if pmh is not None:
                candidates.append(("PMH", pmh, "resistance"))
            if pml is not None:
                candidates.append(("PML", pml, "support"))

            # first touch: high/low tags level this bar, and level not yet touched today
            for name, lvl, kind in candidates:
                if not level_allowed_for_entry(name, cfg):
                    continue
                key = round(float(lvl), 2)
                if key in touched:
                    continue
                tagged = lo <= key <= hi
                if not tagged:
                    continue
                # mark touch (even if RSI/rejection fails — first touch is consumed)
                touched.add(key)
                if not rejection_close_ok(
                    kind, price, key, require=cfg.require_rejection_close
                ):
                    continue
                side = signal_side_for_touch(kind, rsi, cfg)
                if side is None:
                    continue
                open_trade = {
                    "side": side,
                    "level_name": name,
                    "level": key,
                    "entry_spot": price,
                    "entry_time": ts,
                    "rsi": rsi,
                    "i": i,
                }
                day_trades += 1
                break

        # force close if still open after window
        if open_trade is not None:
            rest = bars.iloc[open_trade["i"] + 1 :]
            if rest.empty:
                rest = bars.iloc[open_trade["i"] :]
            ep, es, reason, etm = _simulate_premium_path(
                open_trade["side"],
                open_trade["entry_spot"],
                rest["High"].astype(float).tolist(),
                rest["Low"].astype(float).tolist(),
                rest["Close"].astype(float).tolist(),
                list(rest.index),
                entry_prem=entry_prem,
                tp_prem=entry_prem * (1 + cfg.take_profit_pct),
                sl_prem=entry_prem * (1 - cfg.stop_loss_pct),
                delta=delta,
            )
            if reason not in ("take_profit", "stop_loss"):
                c = float(rest["Close"].iloc[-1])
                if open_trade["side"] == "CALL":
                    ep = entry_prem + delta * (c - open_trade["entry_spot"])
                else:
                    ep = entry_prem + delta * (open_trade["entry_spot"] - c)
                ep = max(ep, 0.01)
                es = c
                reason = "time_exit"
                etm = rest.index[-1]
            pnl_pct = (ep - entry_prem) / entry_prem
            pnl_dollars = (ep - entry_prem) * 100 * contracts
            trades.append(
                OdteTrade(
                    day=d.isoformat(),
                    side=open_trade["side"],
                    level_name=open_trade["level_name"],
                    level=open_trade["level"],
                    entry_time=str(open_trade["entry_time"]),
                    exit_time=str(etm),
                    entry_spot=open_trade["entry_spot"],
                    exit_spot=float(es),
                    entry_prem=entry_prem,
                    exit_prem=float(ep),
                    exit_reason=reason,
                    pnl_pct=round(pnl_pct, 4),
                    pnl_dollars=round(pnl_dollars, 2),
                    rsi_at_entry=open_trade["rsi"],
                )
            )
            equity += pnl_dollars
            curve.append(equity)

    winners = [t for t in trades if t.pnl_dollars > 0]
    losers = [t for t in trades if t.pnl_dollars <= 0]
    total = sum(t.pnl_dollars for t in trades)
    gw = sum(t.pnl_dollars for t in winners)
    gl = abs(sum(t.pnl_dollars for t in losers))
    pf = gw / gl if gl else float(gw > 0)

    # max DD on equity curve
    peak = curve[0]
    max_dd = 0.0
    for v in curve:
        peak = max(peak, v)
        max_dd = max(max_dd, peak - v)

    by_side: Dict[str, Dict[str, float]] = {}
    for side in ("CALL", "PUT"):
        st = [t for t in trades if t.side == side]
        if not st:
            continue
        w = sum(1 for t in st if t.pnl_dollars > 0)
        by_side[side] = {
            "count": float(len(st)),
            "win_rate": w / len(st),
            "total_pnl": sum(t.pnl_dollars for t in st),
        }
    by_exit: Dict[str, int] = defaultdict(int)
    for t in trades:
        by_exit[t.exit_reason] += 1

    return OdteBacktestResult(
        symbol=symbol,
        days=len(days),
        trade_count=len(trades),
        winners=len(winners),
        losers=len(losers),
        win_rate=round(len(winners) / len(trades), 4) if trades else 0.0,
        total_pnl=round(total, 2),
        expectancy=round(total / len(trades), 2) if trades else 0.0,
        profit_factor=round(pf, 2),
        max_drawdown=round(max_dd, 2),
        avg_pnl_pct=round(float(np.mean([t.pnl_pct for t in trades])), 4) if trades else 0.0,
        by_side=by_side,
        by_exit=dict(by_exit),
        trades=trades,
        assumptions=[
            "Style: mean_reversion (fade RSI extremes at levels — not OR breakout continuation)",
            f"1m bars period={period}; source={getattr(df, 'attrs', {}).get('data_source', data_source)}",
            f"Synthetic premium ${entry_prem:.2f}; delta={delta} $prem per $1 underlying",
            f"Bracket TP +{cfg.take_profit_pct:.0%} / SL -{cfg.stop_loss_pct * 100:.1f}% on premium",
            f"Contracts={contracts} (×100 multiplier); max {max_trades_per_day} trades/day",
            "First touch of level + RSI extreme + 9:30–11:15 ET window only",
            (
                "Levels: structural PD/PM/OR only"
                if not cfg.use_whole_dollar_levels
                else "Levels: structural PD/PM/OR + whole-dollar rails"
            ),
            (
                "Require rejection close on signal bar"
                if cfg.require_rejection_close
                else "No rejection-close filter"
            ),
            "Not full options IV/chain model — relative success rate under this proxy",
        ],
        metadata={
            "period": period,
            "style": "mean_reversion",
            "data_source": getattr(df, "attrs", {}).get("data_source", data_source),
            "put_rsi": cfg.put_rsi,
            "call_rsi": cfg.call_rsi,
            "use_whole_dollar_levels": cfg.use_whole_dollar_levels,
            "require_rejection_close": cfg.require_rejection_close,
            "take_profit_pct": cfg.take_profit_pct,
            "stop_loss_pct": cfg.stop_loss_pct,
            "bars": len(df),
        },
    )


def render_odte_backtest(result: OdteBacktestResult) -> str:
    lines = [
        f"# {result.symbol} 0DTE Playbook Backtest",
        "",
        "## Assumptions",
    ]
    for a in result.assumptions:
        lines.append(f"- {a}")
    lines.extend(
        [
            "",
            "## Results",
            f"- **Days covered:** {result.days}",
            f"- **Trades:** {result.trade_count}",
            f"- **Winners / Losers:** {result.winners} / {result.losers}",
            f"- **Win rate (success rate):** **{result.win_rate:.1%}**",
            f"- **Total P/L:** ${result.total_pnl:+,.2f}",
            f"- **Expectancy:** ${result.expectancy:+,.2f} / trade",
            f"- **Avg P/L % (premium):** {result.avg_pnl_pct:+.1%}",
            f"- **Profit factor:** {result.profit_factor:.2f}",
            f"- **Max drawdown:** ${result.max_drawdown:,.2f}",
            "",
            "## By side",
        ]
    )
    for side, stats in result.by_side.items():
        lines.append(
            f"- **{side}:** n={int(stats['count'])} | WR {stats['win_rate']:.1%} | "
            f"P/L ${stats['total_pnl']:+,.2f}"
        )
    if not result.by_side:
        lines.append("- _No trades_")
    lines.append("")
    lines.append("## Exits")
    for k, v in sorted(result.by_exit.items(), key=lambda x: -x[1]):
        lines.append(f"- {k}: {v}")
    lines.extend(["", "## Sample trades (up to 15)"])
    for t in result.trades[:15]:
        lines.append(
            f"- {t.day} {t.side} {t.level_name} @ {t.level:.2f} | "
            f"RSI {t.rsi_at_entry:.0f} | {t.exit_reason} | "
            f"{t.pnl_pct:+.1%} | ${t.pnl_dollars:+.2f}"
        )
    if not result.trades:
        lines.append("- _No trades matched the playbook filters in this sample._")
    lines.append("")
    lines.append(
        "_Success rate = winners / trades under synthetic premium model. "
        "Live options P/L will differ with IV crush and spreads._"
    )
    return "\n".join(lines) + "\n"
