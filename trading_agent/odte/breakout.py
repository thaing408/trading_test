"""Breakout / continuation playbook on HTF bars (OR high/low break).

Opposite of Shen mean-reversion (fade RSI extremes at levels):
- CALL when close breaks *above* opening-range high (continuation long)
- PUT when close breaks *below* opening-range low (continuation short)

Uses same synthetic premium path as multi-DTE for apples-to-apples style A/B.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time
from typing import Dict, List, Optional

import numpy as np

from trading_agent.odte.backtest import (
    OdteBacktestResult,
    OdteTrade,
    _day_slice,
    _in_window,
    _prior_day_hl,
    _session_days,
    _simulate_premium_path,
)
from trading_agent.odte.multidte import MultidtePlaybookConfig, fetch_htf_bars
from trading_agent.strategy.style import TradingStyle, format_style_brief


@dataclass
class BreakoutPlaybookConfig(MultidtePlaybookConfig):
    """OR breakout continuation; defaults favor HTF weeklies."""

    # Breakout: allow both sides by default (continuation either way)
    puts_only: bool = False
    calls_only: bool = False
    # Require close *through* OR level (not just wick touch)
    require_close_beyond: bool = True
    # Skip first N minutes after open (OR still measured from 9:30)
    window_start_et: time = time(10, 0)
    window_end_et: time = time(14, 0)
    or_minutes: int = 30
    take_profit_pct: float = 0.25
    stop_loss_pct: float = 0.20
    premium_delta: float = 0.40
    # Breakouts: slightly easier continuation target
    bar_interval: str = "15m"
    target_dte: int = 5


def _or_bar_count(interval: str, or_minutes: int) -> int:
    mins = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60, "1h": 60}.get(
        interval.lower(), 15
    )
    return max(1, int(round(or_minutes / mins)))


def breakout_side_from_close(
    close: float,
    orh: float,
    orl: float,
    *,
    require_close_beyond: bool = True,
    eps: float = 0.01,
) -> Optional[str]:
    """Pure signal: CALL if close breaks ORH, PUT if close breaks ORL."""
    if require_close_beyond:
        if close > orh + eps:
            return "CALL"
        if close < orl - eps:
            return "PUT"
        return None
    # touch mode (weaker)
    if close >= orh:
        return "CALL"
    if close <= orl:
        return "PUT"
    return None


def run_breakout_backtest(
    symbol: str = "QQQ",
    *,
    period: str = "60d",
    cfg: BreakoutPlaybookConfig | None = None,
    entry_prem: float = 1.0,
    contracts: int = 2,
    max_trades_per_day: int = 2,
    df=None,
    data_source: str = "auto",
) -> OdteBacktestResult:
    """Backtest OR breakout continuation (synthetic premium)."""
    cfg = cfg or BreakoutPlaybookConfig(symbol=symbol)
    cfg.symbol = symbol
    delta = float(cfg.premium_delta)

    if df is None:
        df = fetch_htf_bars(
            symbol,
            period=period,
            interval=cfg.bar_interval,
            source=data_source,
        )

    trades: List[OdteTrade] = []
    equity = cfg.account_size
    curve = [equity]
    days = _session_days(df)
    or_bars = _or_bar_count(cfg.bar_interval, cfg.or_minutes)

    for d in days:
        day_df = _day_slice(df, d)
        rth = day_df.between_time(time(9, 30), time(16, 0))
        if len(rth) < or_bars + 3:
            continue
        pdh, pdl = _prior_day_hl(df, d)
        if pdh is None:
            continue
        head = rth.iloc[:or_bars]
        orh = float(head["High"].max())
        orl = float(head["Low"].min())

        open_trade: Optional[dict] = None
        day_trades = 0
        broke_up = False
        broke_down = False

        bars = rth.between_time(cfg.window_start_et, cfg.window_end_et)
        if bars.empty:
            continue
        times = list(bars.index)

        for i, ts in enumerate(times):
            row = bars.iloc[i]
            price = float(row["Close"])
            hi = float(row["High"])
            lo = float(row["Low"])

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
                            rsi_at_entry=0.0,
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
            if open_trade is not None:
                continue

            side = breakout_side_from_close(
                price,
                orh,
                orl,
                require_close_beyond=cfg.require_close_beyond,
            )
            if side is None:
                continue
            if side == "CALL" and (broke_up or cfg.puts_only):
                continue
            if side == "PUT" and (broke_down or cfg.calls_only):
                continue

            level_name = "ORH_break" if side == "CALL" else "ORL_break"
            level = orh if side == "CALL" else orl
            if side == "CALL":
                broke_up = True
            else:
                broke_down = True

            open_trade = {
                "side": side,
                "level_name": level_name,
                "level": round(level, 2),
                "entry_spot": price,
                "entry_time": ts,
                "i": i,
            }
            day_trades += 1

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
                    rsi_at_entry=0.0,
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
            f"Style: {TradingStyle.BREAKOUT.value} (OR break continuation)",
            f"HTF bars period={period} interval={cfg.bar_interval} source={src}",
            f"Target DTE≈{cfg.target_dte}; synthetic premium ${entry_prem:.2f} delta={delta}",
            f"Bracket TP +{cfg.take_profit_pct:.0%} / SL -{cfg.stop_loss_pct * 100:.1f}%",
            f"Window {cfg.window_start_et.strftime('%H:%M')}–{cfg.window_end_et.strftime('%H:%M')} ET; "
            f"OR first {cfg.or_minutes}m; close-beyond={cfg.require_close_beyond}",
            "CALL: close > ORH | PUT: close < ORL (first break per side/day)",
            "Not full options IV/chain — relative success rate under this proxy",
        ],
        metadata={
            "period": period,
            "mode": "breakout",
            "style": TradingStyle.BREAKOUT.value,
            "target_dte": cfg.target_dte,
            "bar_interval": cfg.bar_interval,
            "data_source": src,
            "bars": len(df),
        },
    )


def render_breakout_backtest(result: OdteBacktestResult) -> str:
    from trading_agent.odte.backtest import render_odte_backtest

    text = render_odte_backtest(result)
    text = text.replace(
        f"# {result.symbol} 0DTE Playbook Backtest",
        f"# {result.symbol} Breakout Playbook Backtest (OR continuation, "
        f"{result.metadata.get('bar_interval', '15m')})",
    )
    style_note = format_style_brief(TradingStyle.BREAKOUT)
    return style_note + "\n" + text


@dataclass
class BreakoutSnapshot:
    """Live 888 TI decision inputs (opening-range continuation)."""

    symbol: str
    decision: str  # LONG | SHORT | WAIT | NO_OR | ERROR
    last: Optional[float]
    orh: Optional[float]
    orl: Optional[float]
    or_ready: bool
    in_trade_window: bool
    session_date: str = ""
    asof_et: str = ""
    data_source: str = ""
    bar_interval: str = "15m"
    error: str = ""
    note: str = ""


def compute_breakout_snapshot(
    symbol: str = "QQQ",
    *,
    cfg: BreakoutPlaybookConfig | None = None,
    data_source: str = "auto",
    period: str = "5d",
    now_et: Optional[datetime] = None,
    df=None,
) -> BreakoutSnapshot:
    """Compute OR levels + simple LONG/SHORT/WAIT decision for 888 TI card."""
    from trading_agent.odte.backtest import ET, _day_slice, _session_days

    cfg = cfg or BreakoutPlaybookConfig(symbol=symbol)
    cfg.symbol = symbol.upper().strip()
    now = now_et or datetime.now(ET)
    if now.tzinfo is None:
        now = now.replace(tzinfo=ET)
    else:
        now = now.astimezone(ET)

    try:
        if df is None:
            df = fetch_htf_bars(
                cfg.symbol,
                period=period,
                interval=cfg.bar_interval,
                source=data_source,
            )
        days = _session_days(df)
        if not days:
            return BreakoutSnapshot(
                symbol=cfg.symbol,
                decision="ERROR",
                last=None,
                orh=None,
                orl=None,
                or_ready=False,
                in_trade_window=False,
                error="no session days in bars",
                data_source=str(getattr(df, "attrs", {}).get("data_source") or data_source),
                bar_interval=cfg.bar_interval,
            )
        # Prefer today's RTH session; else last available session (after close / weekend)
        today = now.date()
        d = today if today in days else days[-1]
        day_df = _day_slice(df, d)
        rth = day_df.between_time(time(9, 30), time(16, 0))
        or_n = _or_bar_count(cfg.bar_interval, cfg.or_minutes)
        or_ready = len(rth) >= or_n
        orh = orl = None
        if or_ready:
            head = rth.iloc[:or_n]
            orh = float(head["High"].max())
            orl = float(head["Low"].min())
        last = None
        if not rth.empty:
            last = float(rth["Close"].iloc[-1])
        elif not day_df.empty:
            last = float(day_df["Close"].iloc[-1])

        t_now = now.timetz().replace(tzinfo=None) if False else now.time()
        # Window only meaningful on the session day we're viewing
        in_window = (
            d == today
            and cfg.window_start_et <= t_now <= cfg.window_end_et
        )
        # Before OR complete
        if not or_ready or orh is None or orl is None:
            decision = "NO_OR"
            note = f"Need first {cfg.or_minutes}m of RTH for OR box"
        elif last is None:
            decision = "ERROR"
            note = "No last price"
        else:
            side = breakout_side_from_close(
                last,
                orh,
                orl,
                require_close_beyond=cfg.require_close_beyond,
            )
            if side == "CALL":
                decision = "LONG"
                note = "Close above OR high → continuation long (calls)"
            elif side == "PUT":
                decision = "SHORT"
                note = "Close below OR low → continuation short (puts)"
            else:
                decision = "WAIT"
                note = "Inside OR box — no breakout yet"
            if decision in ("LONG", "SHORT") and d == today and not in_window:
                note += " · outside preferred entry window (still a structure read)"
            if d != today:
                note += f" · levels from last session {d.isoformat()}"

        if cfg.puts_only and decision == "LONG":
            decision = "WAIT"
            note = "Puts-only mode — ignore long breakouts"
        if cfg.calls_only and decision == "SHORT":
            decision = "WAIT"
            note = "Calls-only mode — ignore short breakouts"

        return BreakoutSnapshot(
            symbol=cfg.symbol,
            decision=decision,
            last=last,
            orh=orh,
            orl=orl,
            or_ready=or_ready,
            in_trade_window=in_window,
            session_date=d.isoformat(),
            asof_et=now.strftime("%Y-%m-%d %H:%M ET"),
            data_source=str(getattr(df, "attrs", {}).get("data_source") or data_source),
            bar_interval=cfg.bar_interval,
            note=note,
        )
    except Exception as exc:  # noqa: BLE001
        return BreakoutSnapshot(
            symbol=cfg.symbol,
            decision="ERROR",
            last=None,
            orh=None,
            orl=None,
            or_ready=False,
            in_trade_window=False,
            asof_et=now.strftime("%Y-%m-%d %H:%M ET"),
            data_source=data_source,
            bar_interval=cfg.bar_interval,
            error=str(exc)[:200],
            note="Could not load bars",
        )


def format_888_ti_card(snap: BreakoutSnapshot, *, cfg: BreakoutPlaybookConfig | None = None) -> str:
    """Visually simple 888 TI decision card (Discord / terminal)."""
    cfg = cfg or BreakoutPlaybookConfig(symbol=snap.symbol)
    dec = (snap.decision or "WAIT").upper()
    emoji = {
        "LONG": "🟢 LONG",
        "SHORT": "🔴 SHORT",
        "WAIT": "🟡 WAIT",
        "NO_OR": "⚪ WAIT",
        "ERROR": "⚠️ ERROR",
    }.get(dec, f"🟡 {dec}")

    def _px(x: Optional[float]) -> str:
        if x is None:
            return "—"
        return f"{x:,.2f}"

    # Simple ladder: ORH / last / ORL
    orh_s = _px(snap.orh)
    orl_s = _px(snap.orl)
    last_s = _px(snap.last)
    mid_mark = "●"
    if snap.last is not None and snap.orh is not None and snap.orl is not None:
        if snap.last > snap.orh:
            mid_mark = "▲ LONG zone"
        elif snap.last < snap.orl:
            mid_mark = "▼ SHORT zone"
        else:
            mid_mark = "● inside box"

    # Distance to levels
    dist_lines: list[str] = []
    if snap.last is not None and snap.orh is not None and snap.orl is not None:
        up = snap.orh - snap.last
        dn = snap.last - snap.orl
        if dec == "WAIT" or dec == "NO_OR":
            dist_lines.append(f"  to LONG break:  +{_px(up)}  (need close > ORH)")
            dist_lines.append(f"  to SHORT break: -{_px(dn)}  (need close < ORL)")
        elif dec == "LONG":
            dist_lines.append(f"  above ORH by {_px(snap.last - snap.orh)}")
        elif dec == "SHORT":
            dist_lines.append(f"  below ORL by {_px(snap.orl - snap.last)}")

    action = {
        "LONG": "ACTION → consider CALL / long debit  |  stop if back inside OR",
        "SHORT": "ACTION → consider PUT / short debit  |  stop if back inside OR",
        "WAIT": "ACTION → NO TRADE  |  wait for close outside the box",
        "NO_OR": "ACTION → NO TRADE  |  wait for opening range to print",
        "ERROR": "ACTION → NO TRADE  |  fix data / retry",
    }.get(dec, "ACTION → NO TRADE")

    lines = [
        "╔══════════════════════════════════════╗",
        f"║  888 TI · {snap.symbol:<5} · BREAKOUT      ║",
        "╚══════════════════════════════════════╝",
        "",
        f"  DECISION   {emoji}",
        f"  {action}",
        "",
        "  ── Opening range (box) ──",
        f"       ORH  {orh_s:>10}   ← break above = LONG",
        f"            {mid_mark}",
        f"      LAST  {last_s:>10}",
        f"            │",
        f"       ORL  {orl_s:>10}   ← break below = SHORT",
        "",
    ]
    if dist_lines:
        lines.extend(dist_lines)
        lines.append("")

    lines.extend(
        [
            "  ── One-screen rules ──",
            "  ✅ Trade WITH the break (continuation)",
            "  ❌ Do NOT fade OR with RSI (that’s Shen MR)",
            f"  🛑 Invalid: reclaim back inside OR after break",
            f"  🎯 Bracket: TP +{cfg.take_profit_pct:.0%}  /  SL −{cfg.stop_loss_pct:.0%}"
            f"  ·  DTE~{cfg.target_dte}  ·  {cfg.bar_interval}",
            f"  ⏰ Window: {cfg.window_start_et.strftime('%H:%M')}–"
            f"{cfg.window_end_et.strftime('%H:%M')} ET"
            + ("  · IN WINDOW" if snap.in_trade_window else ""),
            "",
            f"  session {snap.session_date or '—'}  ·  {snap.asof_et or '—'}"
            f"  ·  bars:{snap.data_source or '?'}",
        ]
    )
    if snap.note:
        lines.append(f"  note: {snap.note}")
    if snap.error:
        lines.append(f"  error: {snap.error}")
    lines.append("")
    lines.append("_888 TI card — confirm on chart · not auto-execution · Schwab for live_")
    return "\n".join(lines) + "\n"


def format_breakout_brief(
    symbol: str = "QQQ",
    *,
    cfg: BreakoutPlaybookConfig | None = None,
    data_source: str = "auto",
    period: str = "5d",
    live: bool = True,
) -> str:
    """888 TI decision card (simple visual). Falls back to static card if offline."""
    cfg = cfg or BreakoutPlaybookConfig(symbol=symbol)
    if live:
        snap = compute_breakout_snapshot(
            symbol, cfg=cfg, data_source=data_source, period=period
        )
        return format_888_ti_card(snap, cfg=cfg)

    # Offline / fixture: static visual without prices
    snap = BreakoutSnapshot(
        symbol=cfg.symbol.upper(),
        decision="WAIT",
        last=None,
        orh=None,
        orl=None,
        or_ready=False,
        in_trade_window=False,
        note="Static card (live=False) — pass live data for levels",
        bar_interval=cfg.bar_interval,
    )
    return format_888_ti_card(snap, cfg=cfg)
