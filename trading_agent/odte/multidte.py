"""Multi-DTE QQQ/SPY playbook: weeklies / 2DTE / 3DTE on higher timeframes.

Motivation (from 0DTE 1m A/B on Schwab/TOS):
- Fast QQQ makes 1m RSI + 0DTE gamma a low-quality churn factory.
- Prefer 15m/30m structure, target DTE 2–7 (weeklies), optional puts-only.

Synthetic premium model is labeled in reports — same style as 0DTE backtest but
milder delta (more extrinsic / less same-day gamma proxy).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

import numpy as np

from trading_agent.odte.backtest import (
    OdteBacktestResult,
    OdteTrade,
    _day_slice,
    _in_window,
    _opening_range,
    _premarket_hl,
    _prior_day_hl,
    _session_days,
    _simulate_premium_path,
    _to_et_index,
)
from trading_agent.odte.playbook import (
    OdtePlaybookConfig,
    is_structural_level_name,
    level_allowed_for_entry,
    rejection_close_ok,
    rsi_series,
    signal_side_for_touch,
    whole_dollar_levels,
)

ET = ZoneInfo("America/New_York")


@dataclass
class MultidtePlaybookConfig(OdtePlaybookConfig):
    """Extends 0DTE config with multi-day expiry + HTF defaults."""

    # Target option horizon (calendar days to expiry label — not chain-selected)
    target_dte: int = 5  # weekly-ish; use 2 or 3 for shorter
    # Bar interval for signals (higher TF than 0DTE 1m)
    bar_interval: str = "15m"
    # Wider entry window for multi-DTE (full morning + early afternoon ET)
    window_start_et: time = time(9, 45)  # skip first 15m open noise
    window_end_et: time = time(14, 0)
    # Milder RSI for 15m (less extreme than 1m 74/26)
    put_rsi: float = 70.0
    call_rsi: float = 30.0
    # Wider level tolerance on 15m
    level_tol: float = 0.60
    or_minutes: int = 30  # first 30m range on 15m (~2 bars) approximated via bar count in backtest
    # Bracket: give multi-DTE room (still synthetic)
    take_profit_pct: float = 0.25
    stop_loss_pct: float = 0.20
    use_whole_dollar_levels: bool = True
    require_rejection_close: bool = True
    # 0DTE + multi-DTE TOS A/B: CALL first-touches dragged WR — default puts-only
    puts_only: bool = True
    # Synthetic delta lower than 0DTE (less same-day gamma)
    premium_delta: float = 0.40


def next_friday_dte(asof: date | None = None) -> int:
    """Calendar days until next Friday (weekly options convention)."""
    d = asof or datetime.now(ET).date()
    # Friday = 4
    days_ahead = (4 - d.weekday()) % 7
    if days_ahead == 0:
        # already Friday → this week's weekly is 0DTE-ish; prefer next week for "weekly swing"
        days_ahead = 7
    return days_ahead


def recommend_expiration_label(target_dte: int, asof: date | None = None) -> str:
    """Human label for target expiry (not a broker OCC symbol)."""
    d = asof or datetime.now(ET).date()
    exp = d + timedelta(days=max(target_dte, 0))
    return exp.isoformat()


def fetch_htf_bars(
    symbol: str = "QQQ",
    period: str = "60d",
    interval: str = "15m",
    *,
    source: str = "auto",
):
    """Load higher-timeframe OHLCV (15m/30m/5m) from Schwab or yfinance."""
    src = (source or "auto").strip().lower()
    interval = (interval or "15m").strip().lower()

    if src in ("auto", "schwab", "tos"):
        try:
            from trading_agent.market_data.schwab_ohlcv import (
                fetch_schwab_ohlcv_dataframe,
                schwab_available,
            )

            if src in ("schwab", "tos") or schwab_available():
                # Schwab minute history is periodType=day, max ~10
                schwab_period = "10d"
                if period.endswith("d") and period[:-1].isdigit():
                    schwab_period = f"{min(max(int(period[:-1]), 1), 10)}d"
                df = fetch_schwab_ohlcv_dataframe(
                    symbol,
                    interval=interval if interval != "1h" else "30m",
                    period=schwab_period,
                    extended_hours=False,
                )
                if df is not None and not df.empty:
                    df = df.copy()
                    df.index = _to_et_index(df)
                    df.attrs["data_source"] = "schwab"
                    df.attrs["bar_interval"] = interval
                    return df
                if src in ("schwab", "tos"):
                    raise ValueError(f"No Schwab {interval} history for {symbol}")
        except Exception:
            if src in ("schwab", "tos"):
                raise

    import yfinance as yf

    # yfinance 15m max ~60d
    t = yf.Ticker(symbol)
    yf_interval = "60m" if interval in ("1h", "60m") else interval
    df = t.history(period=period, interval=yf_interval, auto_adjust=True)
    if df is None or df.empty:
        raise ValueError(f"No {interval} history for {symbol}")
    df = df.copy()
    df.index = _to_et_index(df)
    df.attrs["data_source"] = "yfinance"
    df.attrs["bar_interval"] = interval
    return df


def _or_bars_for_interval(interval: str, or_minutes: int) -> int:
    """How many bars ≈ opening-range minutes."""
    mins = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60, "1h": 60}.get(
        interval.lower(), 15
    )
    return max(1, int(round(or_minutes / mins)))


def run_multidte_backtest(
    symbol: str = "QQQ",
    *,
    period: str = "60d",
    cfg: MultidtePlaybookConfig | None = None,
    entry_prem: float = 1.0,
    contracts: int = 2,
    max_trades_per_day: int = 2,
    df=None,
    data_source: str = "auto",
) -> OdteBacktestResult:
    """Backtest HTF level+RSI multi-DTE playbook (synthetic premium)."""
    cfg = cfg or MultidtePlaybookConfig(symbol=symbol)
    cfg.symbol = symbol
    delta = float(cfg.premium_delta)

    if df is None:
        df = fetch_htf_bars(
            symbol,
            period=period,
            interval=cfg.bar_interval,
            source=data_source,
        )

    closes_all = df["Close"].astype(float).tolist()
    rsi_all = rsi_series(closes_all, cfg.rsi_length)
    df = df.copy()
    df["rsi"] = rsi_all

    trades: List[OdteTrade] = []
    equity = cfg.account_size
    curve = [equity]
    days = _session_days(df)
    or_bars = _or_bars_for_interval(cfg.bar_interval, cfg.or_minutes)

    for d in days:
        day_df = _day_slice(df, d)
        rth = day_df.between_time(time(9, 30), time(16, 0))
        if len(rth) < cfg.rsi_length + 3:
            continue
        pdh, pdl = _prior_day_hl(df, d)
        if pdh is None:
            continue
        # opening range from first N RTH bars
        head = rth.iloc[:or_bars]
        orh = float(head["High"].max()) if not head.empty else None
        orl = float(head["Low"].min()) if not head.empty else None
        pmh, pml = _premarket_hl(day_df)

        touched: set[float] = set()
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

            if open_trade is not None:
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
                hit = reason in ("take_profit", "stop_loss")
                end_window = i == len(times) - 1
                if hit or end_window:
                    if not hit and end_window:
                        if open_trade["side"] == "CALL":
                            ep = entry_prem + delta * (price - open_trade["entry_spot"])
                        else:
                            ep = entry_prem + delta * (open_trade["entry_spot"] - price)
                        ep = max(ep, 0.01)
                        es = price
                        reason = "time_exit"
                        etm = ts
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
                        continue
                else:
                    continue

            if day_trades >= max_trades_per_day:
                continue
            if not _in_window(ts.to_pydatetime(), cfg.window_start_et, cfg.window_end_et):
                continue

            candidates: List[Tuple[str, float, str]] = []
            if cfg.use_whole_dollar_levels:
                above, below = whole_dollar_levels(price, n=4)
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

            for name, lvl, kind in candidates:
                if not level_allowed_for_entry(name, cfg):
                    continue
                key = round(float(lvl), 2)
                if key in touched:
                    continue
                if not (lo <= key <= hi):
                    continue
                touched.add(key)
                if not rejection_close_ok(
                    kind, price, key, require=cfg.require_rejection_close
                ):
                    continue
                side = signal_side_for_touch(kind, rsi, cfg)
                if side is None:
                    continue
                if cfg.puts_only and side == "CALL":
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

    exp_label = recommend_expiration_label(cfg.target_dte)
    src = getattr(df, "attrs", {}).get("data_source", data_source)

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
            f"Multi-DTE HTF backtest period={period} interval={cfg.bar_interval} source={src}",
            f"Target DTE≈{cfg.target_dte} (label exp ~{exp_label}); not OCC chain selection",
            f"Synthetic premium ${entry_prem:.2f}; delta={delta} (milder than 0DTE 0.55)",
            f"Bracket TP +{cfg.take_profit_pct:.0%} / SL -{cfg.stop_loss_pct * 100:.1f}% on premium",
            f"Window {cfg.window_start_et.strftime('%H:%M')}–{cfg.window_end_et.strftime('%H:%M')} ET; "
            f"max {max_trades_per_day}/day; puts_only={cfg.puts_only}",
            f"Rejection close={cfg.require_rejection_close}; whole-$={cfg.use_whole_dollar_levels}",
            "Not full options IV/chain — relative success rate under this proxy",
        ],
        metadata={
            "period": period,
            "mode": "multidte",
            "target_dte": cfg.target_dte,
            "bar_interval": cfg.bar_interval,
            "data_source": src,
            "puts_only": cfg.puts_only,
            "premium_delta": delta,
            "bars": len(df),
        },
    )


def render_multidte_backtest(result: OdteBacktestResult) -> str:
    from trading_agent.odte.backtest import render_odte_backtest

    text = render_odte_backtest(result)
    # Retitle for multi-DTE
    dte = result.metadata.get("target_dte", "?")
    iv = result.metadata.get("bar_interval", "?")
    text = text.replace(
        f"# {result.symbol} 0DTE Playbook Backtest",
        f"# {result.symbol} Multi-DTE Playbook Backtest (DTE≈{dte}, {iv})",
    )
    return text


def format_multidte_brief(
    symbol: str = "QQQ",
    *,
    cfg: MultidtePlaybookConfig | None = None,
    last: Optional[float] = None,
    rsi_htf: Optional[float] = None,
) -> str:
    """Static-style brief for multi-DTE desk (levels filled when last provided)."""
    cfg = cfg or MultidtePlaybookConfig(symbol=symbol)
    exp = recommend_expiration_label(cfg.target_dte)
    fri = next_friday_dte()
    lines = [
        f"**{cfg.symbol} Multi-DTE Playbook** (weeklies / 2–3 DTE on HTF)",
        f"_Target DTE≈{cfg.target_dte} → label exp ~{exp} | next Friday in ~{fri}d_",
        f"_Bars: {cfg.bar_interval} | window "
        f"{cfg.window_start_et.strftime('%H:%M')}–{cfg.window_end_et.strftime('%H:%M')} ET_",
        "",
        "**Why not 0DTE as core:** fast QQQ + 1m noise; prefer structure on 15m+ with more extrinsic.",
        "",
        "**Rules:**",
        f"- PUT: resistance first-touch + RSI≥{cfg.put_rsi:.0f}"
        + (" (puts-only mode)" if cfg.puts_only else ""),
        f"- CALL: support first-touch + RSI≤{cfg.call_rsi:.0f}"
        + (" — disabled" if cfg.puts_only else ""),
        f"- Levels: PD/PM/OR"
        + (" + whole-$" if cfg.use_whole_dollar_levels else " only")
        + ("; require rejection close" if cfg.require_rejection_close else ""),
        f"- Bracket template: TP +{cfg.take_profit_pct:.0%} / SL -{cfg.stop_loss_pct * 100:.1f}% "
        f"(synthetic; size ≤ {cfg.max_position_pct:.0%} of ${cfg.account_size:.0f})",
        "",
    ]
    if last is not None:
        lines.append(f"**Last:** ${last:.2f}" + (f" | HTF RSI: {rsi_htf:.1f}" if rsi_htf is not None else ""))
        above, below = whole_dollar_levels(last, n=3)
        lines.append(f"- Whole $ near: above {above[:3]} / below {below[:3]}")
    lines.append(
        "_Educational desk scaffold — not auto-execution; confirm chain liquidity & IV._"
    )
    return "\n".join(lines) + "\n"
