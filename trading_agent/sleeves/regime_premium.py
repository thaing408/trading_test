"""Ablation: desk-style premium path only when regime is chop (not strong trend).

Uses daily SPY returns to tag regime:
  - trend_up: 20d return > +3%
  - trend_down: 20d return < -3%
  - chop: otherwise

Re-runs offline backtest engine with costs; reports P/L on all days vs chop-only
(skipping trades on trend days by zeroing approvals conceptually via filtering
simulated trades after the fact if we only have full run — better: filter at day).

Implementation: run full backtest, then for chop-only keep trades whose entry
day index falls in chop regime.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from trading_agent.backtest.engine import default_sweep_configs, run_backtest, score_period
from trading_agent.backtest.historical import load_historical_ohlcv
from trading_agent.backtest.models import SimulatedTrade


def _spy_regime(closes: Sequence[float], i: int, look: int = 20) -> str:
    if i < look:
        return "chop"
    r = (float(closes[i]) - float(closes[i - look])) / float(closes[i - look])
    if r > 0.03:
        return "trend_up"
    if r < -0.03:
        return "trend_down"
    return "chop"


def run_regime_premium_ablation(
    *,
    period: str = "1y",
    slip_bps: float = 5.0,
    commission: float = 1.0,
) -> Dict[str, Any]:
    ohlcv = load_historical_ohlcv(period=period, min_bars=80)
    if "SPY" not in ohlcv:
        # need SPY for regime — load alone
        extra = load_historical_ohlcv(["SPY"], period=period, min_bars=80)
        ohlcv.update(extra)
    spy_c = list(ohlcv.get("SPY", {}).get("close") or [])
    cfg = replace(
        default_sweep_configs()[0],
        name="premium_regime",
        slippage_bps=slip_bps,
        commission_per_trade=commission,
    )
    full = run_backtest(cfg, ohlcv=ohlcv)

    def tag(t: SimulatedTrade) -> str:
        i = int(t.entry_day_index)
        if not spy_c or i >= len(spy_c):
            return "chop"
        return _spy_regime(spy_c, i)

    by_reg: Dict[str, List[SimulatedTrade]] = {"trend_up": [], "trend_down": [], "chop": []}
    for t in full.trades:
        by_reg.setdefault(tag(t), []).append(t)

    def stats(trades: List[SimulatedTrade]) -> Dict[str, float]:
        if not trades:
            return {"n": 0, "wr": 0.0, "pnl": 0.0, "exp": 0.0}
        wins = sum(1 for t in trades if t.profit_loss > 0)
        pnl = sum(t.profit_loss for t in trades)
        return {
            "n": float(len(trades)),
            "wr": wins / len(trades),
            "pnl": round(pnl, 2),
            "exp": round(pnl / len(trades), 2),
        }

    chop_only = by_reg.get("chop") or []
    trend_days = (by_reg.get("trend_up") or []) + (by_reg.get("trend_down") or [])

    return {
        "full": {
            "n": full.trade_count,
            "wr": full.win_rate,
            "pnl": full.total_pnl,
            "exp": full.expectancy,
            "score": score_period(full),
        },
        "by_regime": {k: stats(v) for k, v in by_reg.items()},
        "chop_only": stats(chop_only),
        "trend_only": stats(trend_days),
        "suggestion": (
            "Prefer premium/IC/CC when SPY 20d regime is chop; "
            "reduce or skip short premium in trend_up/trend_down"
            if stats(chop_only).get("exp", 0) > stats(trend_days).get("exp", -1e9)
            else "Regime split inconclusive on this sample"
        ),
        "period": period,
        "assumptions": [
            "Desk backtest path with book gates + costs",
            "Regime from SPY 20d return ±3%",
            "Chop-only = filter trades after the fact (same signals, skip trend days)",
        ],
    }


def format_regime_report(d: Dict[str, Any]) -> str:
    lines = [
        "# Premium path × market regime ablation",
        "",
        f"Period: {d.get('period')}",
        f"Full: n={d['full']['n']} WR={d['full']['wr']:.1%} "
        f"exp=${d['full']['exp']:+.2f} PnL=${d['full']['pnl']:+.2f}",
        "",
        "## By regime",
        "| Regime | n | WR | Exp | P/L |",
        "|--------|---|-----|-----|-----|",
    ]
    for k, s in (d.get("by_regime") or {}).items():
        lines.append(
            f"| {k} | {int(s['n'])} | {s['wr']:.0%} | ${s['exp']:+.2f} | ${s['pnl']:+.2f} |"
        )
    lines += [
        "",
        f"**Chop-only:** {d.get('chop_only')}",
        f"**Trend-only:** {d.get('trend_only')}",
        "",
        f"**Suggestion:** {d.get('suggestion')}",
        "",
    ]
    return "\n".join(lines) + "\n"
