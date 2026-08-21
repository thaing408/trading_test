#!/usr/bin/env python3
"""One-pass discovery → book export → WR-desk selection backtest.

**Repo: trading_agent (live Mac desk methods).** No order_block (that's methods lab).


Loads 15m bars once, evaluates ALL multi-method votes per symbol-day (no lookahead),
then simulates three selection policies on the same evals:

  A) Discovery: any PLAY (min 1 method)
  B) Book export: passes_export_quality (2 methods + chart_patterns + scores)
  C) WR LIVE: B + CALL-only + method allowlist (patterns/fvg/soulz/swing)

Synthetic option premium: +25% / −20%, same as router BT.
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, time, timedelta
from typing import Dict, List, Tuple
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

os.environ.setdefault("TRADING_AGENT_WR_DESK", "0")
os.environ.setdefault("TRADING_AGENT_EXPORT_REQUIRE_CHART_PATTERNS", "1")

from trading_agent.odte.top_winners import simulate_premium_path_l3
from trading_agent.strategy.multi_method import (
    MultiMethodConfig,
    TickerMultiEval,
    evaluate_ticker_all_methods,
    fetch_bars,
    passes_export_quality,
    pick_execute_vote,
    pick_swing_vote,
)
from trading_agent.strategy.multi_method_backtest import (
    RouterBacktestConfig,
    _path_after,
    _session_days_from_frames,
    _slice_asof,
    _to_et_index,
)

WR_ALLOW = frozenset({"chart_patterns", "fvg", "soulz_pa"})
POOL = [
    "COIN",
    "NVDA",
    "AMD",
    "TSLA",
    "QQQ",
    "SPY",
    "AAPL",
    "MSFT",
    "META",
    "AMZN",
]


def _best_vote(
    ev: TickerMultiEval,
    allow=None,
    call_only=False,
    *,
    wr_execute: bool = False,
    swing: bool = False,
):
    if swing:
        return pick_swing_vote(ev)
    if wr_execute:
        return pick_execute_vote(ev, allow=allow or WR_ALLOW, call_only=True)
    votes = [v for v in ev.votes if v.play and v.method_id != "process_methods"]
    if allow is not None:
        votes = [v for v in votes if v.method_id in allow]
    if call_only:
        votes = [v for v in votes if (v.side or ev.best_side or "CALL").upper() != "PUT"]
    if not votes:
        return None
    return max(votes, key=lambda v: float(v.score))


def _path_for(df, d, decision_time: time, mode: str):
    """eod = same day through 15:45; overnight = through next session 10:30 (gap)."""
    cutoff = datetime.combine(d, decision_time, tzinfo=ET)
    if mode == "eod":
        eod = datetime.combine(d, time(15, 45), tzinfo=ET)
        mask = [(ts > cutoff and ts.date() == d and ts <= eod) for ts in df.index]
        sub = df.loc[mask]
        return sub if sub is not None and len(sub) else None
    if mode == "overnight":
        nxt = d + timedelta(days=1)
        while nxt.weekday() >= 5:
            nxt += timedelta(days=1)
        end = datetime.combine(nxt, time(10, 30), tzinfo=ET)
        mask = []
        for ts in df.index:
            try:
                tts = ts.tz_convert(ET) if getattr(ts, "tzinfo", None) else ts
            except Exception:
                tts = ts
            mask.append(bool(tts > cutoff and tts <= end))
        sub = df.loc[mask]
        if sub is None or len(sub) == 0:
            return None
        # 15:00→close + next open→10:30 on 15m is << 30 bars; cap runaway index
        if len(sub) > 28:
            sub = sub.iloc[:28]
        return sub
    return _path_after(df, d, decision_time, 20)


def _simulate(ev, best, df, d, bt: RouterBacktestConfig, *, path_mode: str = "default"):
    entry_spot = float(best.entry or 0)
    if entry_spot <= 0:
        sub = _slice_asof(df, d, bt.decision_time_et)
        if sub is None or len(sub) == 0:
            return None
        entry_spot = float(sub["Close"].iloc[-1])
    side = (best.side or ev.best_side or "CALL").upper()
    if side not in ("CALL", "PUT"):
        side = "CALL"
    path_df = _path_for(df, d, bt.decision_time_et, path_mode)
    if path_df is None or len(path_df) < 1:
        return None
    highs = path_df["High"].astype(float).tolist()
    lows = path_df["Low"].astype(float).tolist()
    closes = path_df["Close"].astype(float).tolist()
    times = list(path_df.index)
    # Overnight path is already clipped to next 10:30. Do not pass 10:30 as
    # a clock (15:15 >= 10:30 would flatten same-day, or fail-open to last bar).
    t_exit = time(15, 45) if path_mode == "eod" else (
        None if path_mode == "overnight" else bt.time_exit_et
    )
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
        time_exit_et=t_exit,
        use_trail=bt.use_trail,
        trail_activate_pct=bt.trail_activate_pct,
        trail_giveback_pct=bt.trail_giveback_pct,
    )
    pnl = (ep - bt.entry_prem) * 100 * bt.contracts
    return {
        "day": d.isoformat(),
        "symbol": ev.symbol,
        "method": best.method_id,
        "plays": ",".join(ev.play_methods or []),
        "side": side,
        "pnl": round(pnl, 2),
        "reason": reason,
        "score": round(float(best.score), 1),
    }


def _stats(rows: List[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"n": 0, "wr": 0.0, "exp": 0.0, "pnl": 0.0, "by_method": {}}
    wins = sum(1 for r in rows if r["pnl"] > 0)
    pnl = sum(r["pnl"] for r in rows)
    by_m: Dict[str, List[float]] = defaultdict(list)
    for r in rows:
        by_m[r["method"]].append(r["pnl"])
    by_method = {
        m: {
            "n": len(v),
            "wr": sum(1 for x in v if x > 0) / len(v),
            "pnl": sum(v),
        }
        for m, v in sorted(by_m.items())
    }
    return {
        "n": n,
        "wr": wins / n,
        "exp": pnl / n,
        "pnl": pnl,
        "by_method": by_method,
    }


def main() -> int:
    period, interval = "30d", "15m"
    rcfg = MultiMethodConfig(
        min_method_score=55.0,
        min_play_methods=1,
        bar_period=period,
        bar_interval=interval,
        data_source="yfinance",
        use_htf_bias=False,
        export_min_play_methods=2,
        export_min_best_score=65.0,
        export_min_play_avg_score=65.0,
        export_require_chart_patterns=True,
    )
    bt = RouterBacktestConfig()
    frames = {}
    errors = []
    print(f"Loading {len(POOL)} symbols {period} {interval}…", flush=True)
    for sym in POOL:
        try:
            df = fetch_bars(sym, period=period, interval=interval, source="yfinance")
            df = df.copy()
            df.index = _to_et_index(df)
            frames[sym] = df
            print(f"  {sym} bars={len(df)}", flush=True)
        except Exception as exc:
            errors.append(f"{sym}:{exc}")
            print(f"  {sym} FAIL {exc}", flush=True)
    days = _session_days_from_frames(frames)
    print(f"Days={len(days)} evals≈{len(days)*len(frames)}", flush=True)

    vote_counts: Dict[str, int] = defaultdict(int)
    disc, book, wr, wr_eod, swing_ovn = [], [], [], [], []
    qcfg = MultiMethodConfig(
        export_min_play_methods=2,
        export_min_best_score=65.0,
        export_min_play_avg_score=65.0,
        export_require_chart_patterns=True,
    )

    for d in days:
        evals: List[TickerMultiEval] = []
        for sym, df in frames.items():
            sub = _slice_asof(df, d, time(15, 0))
            if sub is None or len(sub) < 15:
                continue
            try:
                ev = evaluate_ticker_all_methods(sym, cfg=rcfg, df=sub)
            except Exception:
                continue
            evals.append(ev)
            for v in ev.votes:
                if v.play and v.method_id != "process_methods":
                    vote_counts[v.method_id] += 1

        plays = [e for e in evals if e.play and e.decision == "PLAY"]

        def take(
            cands,
            allow=None,
            call_only=False,
            max_n=20,
            wr_execute=False,
            path_mode="default",
            swing=False,
        ):
            rows = []
            per: Dict[str, int] = defaultdict(int)
            ranked = []
            for e in cands:
                b = _best_vote(
                    e,
                    allow=allow,
                    call_only=call_only,
                    wr_execute=wr_execute,
                    swing=swing,
                )
                if b is None:
                    continue
                ranked.append((float(b.score), e, b))
            ranked.sort(key=lambda x: -x[0])
            for _sc, e, b in ranked:
                if len(rows) >= max_n:
                    break
                if per[e.symbol] >= 2:
                    continue
                sim = _simulate(e, b, frames[e.symbol], d, bt, path_mode=path_mode)
                if not sim:
                    continue
                rows.append(sim)
                per[e.symbol] += 1
            return rows

        disc.extend(take(plays, allow=None, call_only=False))
        exported = []
        for e in plays:
            ok, _ = passes_export_quality(e, cfg=qcfg)
            if ok:
                exported.append(e)
        book.extend(take(exported, allow=None, call_only=False))
        wr.extend(take(exported, allow=WR_ALLOW, call_only=True, wr_execute=True))
        wr_eod.extend(
            take(exported, allow=WR_ALLOW, call_only=True, wr_execute=True, path_mode="eod")
        )
        swing_ovn.extend(
            take(plays, swing=True, path_mode="overnight")
        )

    def block(name, st):
        lines = [
            f"## {name}",
            f"n={st['n']}  WR={st['wr']:.1%}  exp=${st['exp']:.2f}  PnL=${st['pnl']:.0f}  (synth $1 prem ×100)",
            "",
            "| Method | n | WR | PnL |",
            "|--------|---|----|-----|",
        ]
        for m, v in st["by_method"].items():
            lines.append(f"| `{m}` | {v['n']} | {v['wr']:.0%} | ${v['pnl']:.0f} |")
        lines.append("")
        return "\n".join(lines)

    sa, sb, sc = _stats(disc), _stats(book), _stats(wr)
    se, ss = _stats(wr_eod), _stats(swing_ovn)
    out = [
        "# Full-stack discovery backtest — trading_agent (live desk)",
        "",
        f"Pool: `{', '.join(POOL)}`",
        f"Period **{period}** 15m yfinance · decision 15:00 ET · no lookahead.",
        "Premium path +25% / −20% (same as multi-method router BT).",
        f"Load errors: {errors or 'none'}",
        "",
        "### Method PLAY votes (all symbol-days, before picking a trade)",
        "",
        "| Method | PLAY votes |",
        "|--------|------------|",
    ]
    for m, n in sorted(vote_counts.items(), key=lambda kv: -kv[1]):
        out.append(f"| `{m}` | {n} |")
    out += [
        "",
        "### Policies",
        "",
        block("A — Discovery (any PLAY, min 1 method)", sa),
        block("B — Book export (2 methods + chart_patterns + score gate)", sb),
        block("C — same-day book (B + CALL + patterns/fvg/soulz; skip if swing-led)", sc),
        block("C+EOD flatten 15:45 (same-day book, no overnight)", se),
        block("S — swing book (swing_daily only, hold overnight → next 10:30)", ss),
        "### Read",
        "- A = what scanners *see*.",
        "- B = what would land in `auto_trade_book` (same-day).",
        "- C = same-day WR execute (patterns/soulz/fvg; no swing substitute).",
        "- C+EOD = flatten 15:45 same day.",
        "- S = sidecar `auto_trade_book_swing.json` (overnight hold, DTE≥7).",
        "- Cash/chop tape is **not** in this BT (session flag).",
        "",
    ]
    text = "\n".join(out)
    path = "docs/full_stack_discovery_bt.md"
    from pathlib import Path

    Path(path).write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"wrote {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
