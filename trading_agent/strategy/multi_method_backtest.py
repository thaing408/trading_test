"""Historical multi-method router backtest.

Each RTH day:
  1. Slice every symbol's bars to end of that day (no lookahead).
  2. Run full multi-method evaluation on that slice.
  3. Pick the best PLAY (highest score / aggregate).
  4. Simulate synthetic option premium path after decision bar.

Default: up to **2 round-trips per symbol per day**; different tickers can all trade
(book-wide cap is high so one name's 2 trips do not end the day for everyone).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, time
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

import numpy as np

from trading_agent.odte.backtest import OdteBacktestResult, OdteTrade, _to_et_index
from trading_agent.odte.top_winners import simulate_premium_path_l3
from trading_agent.strategy.multi_method import (
    MultiMethodConfig,
    TickerMultiEval,
    evaluate_ticker_all_methods,
    fetch_bars,
)

ET = ZoneInfo("America/New_York")


@dataclass
class RouterBacktestConfig:
    # Book-wide cap (high default so different tickers are not blocked after 2 total)
    max_trades_per_day: int = 20
    # Strict cap only for the same ticker (user re-entry / 2 round trips)
    max_trades_per_symbol_per_day: int = 2
    decision_time_et: time = time(15, 0)  # evaluate as-of this time (or last bar before)
    take_profit_pct: float = 0.25
    stop_loss_pct: float = 0.20
    premium_delta: float = 0.45
    entry_prem: float = 1.0
    contracts: int = 1
    use_trail: bool = True
    trail_activate_pct: float = 0.12
    trail_giveback_pct: float = 0.08
    time_exit_et: time = time(15, 55)
    hold_max_bars: int = 20
    min_method_score: float = 55.0
    min_play_methods: int = 1
    require_two: bool = False
    # Export-quality style filters (match multi_method export gate)
    require_export_quality: bool = False
    min_best_play_score: float = 65.0
    min_play_avg_score: float = 65.0
    # Rank / select: multiply best-method score by weight (swing_daily was flooding the book)
    method_rank_weights: Dict[str, float] = field(
        default_factory=lambda: {
            "swing_daily": 0.45,
            "chart_patterns": 1.15,
            "top_winners": 1.1,
            "soulz_pa": 1.05,
            "fvg": 1.0,
            "order_block": 1.0,
            "sweep": 1.0,
            "orb_vwap": 0.95,
            "odte_breakout": 0.9,
            "range_fade": 0.9,
            "process_methods": 0.0,
        }
    )
    # If True, never pick swing_daily as sole best unless another play method score ≥ min_best
    swing_needs_confluence: bool = True


def _session_days_from_frames(frames: Dict[str, Any]) -> List[date]:
    days: set[date] = set()
    for df in frames.values():
        if df is None or len(df) == 0:
            continue
        rth = df.between_time(time(9, 30), time(16, 0))
        use = rth if len(rth) else df
        for ts in use.index:
            days.add(ts.date())
    return sorted(days)


def _slice_asof(df, d: date, decision_time: time):
    """Bars from start through decision time on day d (inclusive)."""
    if df is None or len(df) == 0:
        return None
    # all bars on or before decision timestamp
    from datetime import datetime

    cutoff = datetime.combine(d, decision_time, tzinfo=ET)
    # keep history before day for structure/OR
    mask = [ts <= cutoff for ts in df.index]
    sub = df.loc[mask]
    if sub is None or len(sub) < 10:
        return None
    # need some bars on day d itself
    on_day = [ts for ts in sub.index if ts.date() == d]
    if not on_day:
        return None
    return sub


def _path_after(df, d: date, decision_time: time, hold_max_bars: int):
    """Bars after decision for exit simulation (same day preferred)."""
    from datetime import datetime

    cutoff = datetime.combine(d, decision_time, tzinfo=ET)
    after = df.loc[[ts > cutoff and ts.date() == d for ts in df.index]]
    if after is None or len(after) == 0:
        # fall through to next session bars
        after = df.loc[[ts > cutoff for ts in df.index]]
    if after is None or len(after) == 0:
        return None
    return after.iloc[:hold_max_bars]


def run_multi_method_backtest(
    symbols: Sequence[str],
    *,
    period: str = "30d",
    interval: str = "15m",
    data_source: str = "yfinance",
    router_cfg: MultiMethodConfig | None = None,
    bt_cfg: RouterBacktestConfig | None = None,
) -> OdteBacktestResult:
    """Walk days; take up to max_trades_per_day best multi-method PLAYs."""
    bt = bt_cfg or RouterBacktestConfig()
    rcfg = router_cfg or MultiMethodConfig(
        min_method_score=bt.min_method_score,
        min_play_methods=2 if bt.require_two else bt.min_play_methods,
        bar_period=period,
        bar_interval=interval,
        data_source=data_source,
        use_htf_bias=True,
        htf_strict=False,
    )
    # Avoid slow daily yfinance HTF inside every symbol-day: structure on slice is enough
    # (evaluate still may try daily — disable for BT speed)
    rcfg.use_htf_bias = False

    pool = [str(s).upper().strip() for s in symbols if str(s).strip()]
    frames: Dict[str, Any] = {}
    load_errors: List[str] = []
    for sym in pool:
        try:
            df = fetch_bars(sym, period=period, interval=interval, source=data_source)
            df = df.copy()
            df.index = _to_et_index(df)
            frames[sym] = df
        except Exception as exc:  # noqa: BLE001
            load_errors.append(f"{sym}: {exc}")

    if not frames:
        return OdteBacktestResult(
            symbol="MULTI_METHOD",
            days=0,
            trade_count=0,
            winners=0,
            losers=0,
            win_rate=0.0,
            total_pnl=0.0,
            expectancy=0.0,
            profit_factor=0.0,
            max_drawdown=0.0,
            avg_pnl_pct=0.0,
            assumptions=["No data loaded"],
            metadata={"errors": load_errors},
        )

    days = _session_days_from_frames(frames)
    trades: List[OdteTrade] = []
    equity = 0.0
    curve = [0.0]
    day_play_counts: Dict[str, int] = defaultdict(int)
    method_wins: Dict[str, int] = defaultdict(int)
    method_trades: Dict[str, int] = defaultdict(int)
    days_with_play = 0

    for d in days:
        # Evaluate each symbol as-of decision time
        day_evals: List[TickerMultiEval] = []
        for sym, df in frames.items():
            sub = _slice_asof(df, d, bt.decision_time_et)
            if sub is None or len(sub) < 15:
                continue
            try:
                ev = evaluate_ticker_all_methods(sym, cfg=rcfg, df=sub)
                day_evals.append(ev)
            except Exception:
                continue

        plays = [e for e in day_evals if e.play and e.decision == "PLAY"]
        if not plays:
            continue
        days_with_play += 1

        # Export-quality filter (same idea as auto_trade export gate)
        if bt.require_export_quality:
            from trading_agent.strategy.multi_method import (
                MultiMethodConfig,
                compute_play_quality,
                passes_export_quality,
            )

            qcfg = MultiMethodConfig(
                export_min_play_methods=int(bt.min_play_methods or 2),
                export_min_best_score=float(bt.min_best_play_score),
                export_min_play_avg_score=float(bt.min_play_avg_score),
            )
            filtered: List[TickerMultiEval] = []
            for e in plays:
                best_sc, avg_sc, _ = compute_play_quality(e)
                e.best_play_score = best_sc
                e.play_quality_score = avg_sc
                ok, _why = passes_export_quality(e, cfg=qcfg)
                if ok:
                    filtered.append(e)
            plays = filtered
            if not plays:
                continue

        wmap = bt.method_rank_weights or {}

        def _best_play_vote(e: TickerMultiEval):
            """Best play vote after rank weights; may prefer non-swing if confluence required."""
            play_votes = [
                v
                for v in e.votes
                if v.play and v.method_id != "process_methods" and v.side in ("CALL", "PUT", "")
            ]
            if not play_votes:
                return None
            # Weighted ranking score
            ranked = sorted(
                play_votes,
                key=lambda v: float(v.score) * float(wmap.get(v.method_id, 1.0)),
                reverse=True,
            )
            top = ranked[0]
            if (
                bt.swing_needs_confluence
                and top.method_id == "swing_daily"
                and float(top.score) < float(bt.min_best_play_score)
            ):
                # Prefer next non-swing method if any is strong enough
                for v in ranked[1:]:
                    if v.method_id != "swing_daily" and float(v.score) >= float(
                        bt.min_method_score
                    ):
                        return v
                # Or require another method also PLAY with decent score
                others = [v for v in ranked if v.method_id != "swing_daily"]
                if not others:
                    return None  # pure swing-only weak → skip
            return top

        def _rank_key(e: TickerMultiEval):
            bv = _best_play_vote(e)
            if bv is None:
                return (-1.0, -1.0)
            w = float(wmap.get(bv.method_id, 1.0))
            return (float(bv.score) * w, e.aggregate_score)

        plays = [e for e in plays if _best_play_vote(e) is not None]
        if not plays:
            continue
        plays.sort(key=_rank_key, reverse=True)
        taken = 0
        taken_by_symbol: Dict[str, int] = defaultdict(int)
        for ev in plays:
            if taken >= bt.max_trades_per_day:
                break
            sym_u = str(ev.symbol or "").upper()
            # Per-ticker cap only — other names still eligible
            if taken_by_symbol[sym_u] >= int(bt.max_trades_per_symbol_per_day or 0):
                continue
            df = frames.get(ev.symbol)
            if df is None:
                continue
            # resolve best vote levels (weighted / swing-aware)
            best = _best_play_vote(ev)
            if best is None:
                continue
            entry_spot = float(best.entry or 0)
            if entry_spot <= 0:
                # last close on slice
                sub = _slice_asof(df, d, bt.decision_time_et)
                if sub is None or len(sub) == 0:
                    continue
                entry_spot = float(sub["Close"].iloc[-1])
            side = (best.side or ev.best_side or "CALL").upper()
            if side not in ("CALL", "PUT"):
                side = "CALL"

            path_df = _path_after(df, d, bt.decision_time_et, bt.hold_max_bars)
            if path_df is None or len(path_df) < 1:
                continue
            highs = path_df["High"].astype(float).tolist()
            lows = path_df["Low"].astype(float).tolist()
            closes = path_df["Close"].astype(float).tolist()
            times = list(path_df.index)
            ep, exit_spot, reason, exit_tm = simulate_premium_path_l3(
                side,
                entry_spot,
                highs,
                lows,
                closes,
                times,
                entry_prem=bt.entry_prem,
                tp_pct=bt.take_profit_pct,
                sl_pct=bt.stop_loss_pct,
                delta=bt.premium_delta,
                time_exit_et=bt.time_exit_et,
                use_trail=bt.use_trail,
                trail_activate_pct=bt.trail_activate_pct,
                trail_giveback_pct=bt.trail_giveback_pct,
            )
            pnl_pct = (ep - bt.entry_prem) / bt.entry_prem
            pnl_dollars = (ep - bt.entry_prem) * 100 * bt.contracts
            equity += pnl_dollars
            curve.append(equity)
            method_trades[best.method_id] += 1
            if pnl_dollars > 0:
                method_wins[best.method_id] += 1
            entry_ts = times[0] if times else d.isoformat()
            # use decision bar time approx
            sub = _slice_asof(df, d, bt.decision_time_et)
            if sub is not None and len(sub):
                entry_ts = sub.index[-1]
            exit_s = exit_tm.isoformat() if hasattr(exit_tm, "isoformat") else str(exit_tm)
            trades.append(
                OdteTrade(
                    day=d.isoformat(),
                    side=side,
                    level_name=(
                        f"router:{best.method_id}+{','.join(ev.play_methods)}"
                        f"|best_sc={best.score:.0f}"
                    ),
                    level=entry_spot,
                    entry_time=entry_ts.isoformat() if hasattr(entry_ts, "isoformat") else str(entry_ts),
                    exit_time=exit_s,
                    entry_spot=entry_spot,
                    exit_spot=float(exit_spot),
                    entry_prem=bt.entry_prem,
                    exit_prem=float(ep),
                    exit_reason=reason,
                    pnl_pct=round(pnl_pct, 4),
                    pnl_dollars=round(pnl_dollars, 2),
                    rsi_at_entry=float(ev.aggregate_score),
                )
            )
            taken += 1
            taken_by_symbol[sym_u] += 1
            day_play_counts[d.isoformat()] += 1

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

    by_method = {
        m: {
            "trades": method_trades[m],
            "wins": method_wins[m],
            "wr": (method_wins[m] / method_trades[m]) if method_trades[m] else 0.0,
        }
        for m in sorted(method_trades.keys())
    }

    return OdteBacktestResult(
        symbol="MULTI_METHOD_ROUTER",
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
            "Multi-method router historical BT: evaluate all methods per symbol as-of decision time",
            f"Decision time ET={bt.decision_time_et.strftime('%H:%M')}; "
            f"max_trades/day={bt.max_trades_per_day} "
            f"(max {bt.max_trades_per_symbol_per_day}/symbol)",
            f"Pool={pool}",
            f"min_method_score={rcfg.min_method_score}; min_play_methods={rcfg.min_play_methods}",
            (
                f"export_quality={'on' if bt.require_export_quality else 'off'} "
                f"(best≥{bt.min_best_play_score:.0f} or avg≥{bt.min_play_avg_score:.0f})"
            ),
            (
                f"swing_weight={float((bt.method_rank_weights or {}).get('swing_daily', 1.0)):.2f}; "
                f"swing_needs_confluence={bt.swing_needs_confluence}"
            ),
            f"Period={period}; interval={interval}; source={data_source}",
            f"Synthetic premium ${bt.entry_prem:.2f} delta={bt.premium_delta}; "
            f"TP +{bt.take_profit_pct:.0%} / SL −{bt.stop_loss_pct:.0%}; trail={'on' if bt.use_trail else 'off'}",
            f"Days with ≥1 PLAY eval: {days_with_play}/{len(days)} "
            f"({(days_with_play/len(days)*100 if days else 0):.0f}%)",
            "HTF daily fetch disabled in BT (structure on LTF slice only)",
            "No lookahead: slice ends at decision time each day",
        ]
        + ([f"Load errors: {'; '.join(load_errors[:5])}"] if load_errors else []),
        metadata={
            "style": "multi_method_router_bt",
            "pool": pool,
            "period": period,
            "interval": interval,
            "days_with_play": days_with_play,
            "days_total": len(days),
            "pct_days_with_play": round(days_with_play / len(days), 4) if days else 0.0,
            "by_method": by_method,
            "max_trades_per_day": bt.max_trades_per_day,
            "max_trades_per_symbol_per_day": bt.max_trades_per_symbol_per_day,
            "decision_time_et": bt.decision_time_et.strftime("%H:%M"),
            "errors": load_errors,
        },
    )


def render_multi_method_backtest(result: OdteBacktestResult) -> str:
    from trading_agent.odte.backtest import render_odte_backtest

    text = render_odte_backtest(result)
    lines = text.splitlines()
    if lines:
        lines[0] = "# Multi-Method Router Historical Backtest"
    by_method = (result.metadata or {}).get("by_method") or {}
    if by_method:
        lines.append("")
        lines.append("## By best-method (selected trades)")
        for m, st in sorted(by_method.items(), key=lambda x: -x[1].get("trades", 0)):
            lines.append(
                f"- **{m}**: n={st.get('trades', 0)} · WR {st.get('wr', 0):.1%} · "
                f"wins={st.get('wins', 0)}"
            )
    meta = result.metadata or {}
    lines.append("")
    lines.append("## Daily hit rate")
    lines.append(
        f"- Days with ≥1 PLAY before selection: "
        f"**{meta.get('days_with_play', 0)}/{meta.get('days_total', 0)}** "
        f"({100 * float(meta.get('pct_days_with_play') or 0):.0f}%)"
    )
    lines.append(
        f"- Trades taken: **{result.trade_count}** "
        f"(max {meta.get('max_trades_per_day', 1)}/day @ {meta.get('decision_time_et', '?')} ET)"
    )
    lines.append("")
    lines.append(
        "_Router BT picks best PLAY per day across methods/symbols; "
        "synthetic premium — not live fills._"
    )
    return "\n".join(lines) + "\n"
