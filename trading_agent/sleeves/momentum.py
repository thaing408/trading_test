"""Cross-sectional momentum / relative strength sleeve (daily).

Classic approach: rank liquid names by 60d return (skip last 5d to reduce
reversal noise); hold top-K equal weight; exit if drops out of top half or
hits ATR stop. Compared to SPY buy-hold over same window.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

ASSUMPTIONS = [
    "Daily bars (yfinance or Schwab via historical loader)",
    "Signal: 60d return excluding most recent 5d; rebalance weekly (every 5 bars)",
    "Hold top 3 of universe; equal weight; 100 shares notional unit per name for $ P/L",
    "Exit: leave top half of ranks OR close < entry - 2*ATR14",
    "No costs in base; optional 5 bps round-trip applied in report",
]


@dataclass
class MomTrade:
    symbol: str
    entry_idx: int
    exit_idx: int
    entry: float
    exit: float
    pnl: float
    reason: str


@dataclass
class MomentumBacktestResult:
    symbols: List[str]
    trade_count: int
    winners: int
    losers: int
    win_rate: float
    total_pnl: float
    expectancy: float
    spy_buy_hold_pnl: float
    beat_spy: bool
    trades: List[MomTrade] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


def _atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], i: int, n: int = 14) -> float:
    if i < 1:
        return 0.0
    trs = []
    for j in range(max(1, i - n + 1), i + 1):
        tr = max(
            highs[j] - lows[j],
            abs(highs[j] - closes[j - 1]),
            abs(lows[j] - closes[j - 1]),
        )
        trs.append(tr)
    return sum(trs) / len(trs) if trs else 0.0


def run_momentum_backtest(
    symbols: Optional[Sequence[str]] = None,
    *,
    period: str = "1y",
    top_k: int = 3,
    lookback: int = 60,
    skip: int = 5,
    rebalance_every: int = 5,
    slip_bps: float = 5.0,
) -> MomentumBacktestResult:
    from trading_agent.backtest.historical import load_historical_ohlcv

    universe = [s.upper() for s in (symbols or [
        "QQQ", "SPY", "IWM", "AAPL", "MSFT", "NVDA", "AMD", "META", "AMZN", "TSLA", "JPM",
    ])]
    ohlcv = load_historical_ohlcv(universe, period=period, min_bars=lookback + 20)
    syms = [s for s in universe if s in ohlcv]
    if "SPY" not in ohlcv and syms:
        # still ok
        pass
    n = min(len(ohlcv[s]["close"]) for s in syms) if syms else 0

    def mom_score(sym: str, i: int) -> float:
        c = ohlcv[sym]["close"]
        if i < lookback + skip:
            return float("-inf")
        # return from i-lookback-skip to i-skip
        a = float(c[i - lookback - skip])
        b = float(c[i - skip])
        if a <= 0:
            return float("-inf")
        return (b - a) / a

    open_pos: Dict[str, Dict[str, float]] = {}
    trades: List[MomTrade] = []
    start = lookback + skip + 5

    for i in range(start, n - 1):
        # exits every bar
        to_close = []
        scores_now = {s: mom_score(s, i) for s in syms}
        ranked = sorted(scores_now.keys(), key=lambda s: scores_now[s], reverse=True)
        top_half = set(ranked[: max(1, len(ranked) // 2)])

        for sym, pos in list(open_pos.items()):
            c = float(ohlcv[sym]["close"][i])
            h = float((ohlcv[sym].get("high") or ohlcv[sym]["close"])[i])
            l = float((ohlcv[sym].get("low") or ohlcv[sym]["close"])[i])
            atr = _atr(
                ohlcv[sym].get("high") or ohlcv[sym]["close"],
                ohlcv[sym].get("low") or ohlcv[sym]["close"],
                ohlcv[sym]["close"],
                i,
            )
            stop = pos["entry"] - 2 * atr
            reason = None
            if l <= stop:
                reason = "atr_stop"
                exit_px = stop
            elif sym not in top_half:
                reason = "rank_exit"
                exit_px = c
            else:
                continue
            pnl = (exit_px - pos["entry"]) * 100
            # costs
            pnl -= abs(pos["entry"] * 100) * (slip_bps / 10000) * 2
            trades.append(
                MomTrade(
                    symbol=sym,
                    entry_idx=int(pos["idx"]),
                    exit_idx=i,
                    entry=pos["entry"],
                    exit=exit_px,
                    pnl=round(pnl, 2),
                    reason=reason,
                )
            )
            to_close.append(sym)
        for sym in to_close:
            del open_pos[sym]

        # rebalance entries
        if (i - start) % rebalance_every != 0:
            continue
        picks = [s for s in ranked[:top_k] if scores_now[s] > float("-inf") and scores_now[s] > 0]
        for sym in picks:
            if sym in open_pos:
                continue
            if len(open_pos) >= top_k:
                break
            entry = float(ohlcv[sym]["close"][i])
            open_pos[sym] = {"entry": entry, "idx": float(i)}

    # force close end
    for sym, pos in open_pos.items():
        c = float(ohlcv[sym]["close"][n - 1])
        pnl = (c - pos["entry"]) * 100
        pnl -= abs(pos["entry"] * 100) * (slip_bps / 10000) * 2
        trades.append(
            MomTrade(
                symbol=sym,
                entry_idx=int(pos["idx"]),
                exit_idx=n - 1,
                entry=pos["entry"],
                exit=c,
                pnl=round(pnl, 2),
                reason="eod",
            )
        )

    # SPY buy hold 100 shares
    spy_pnl = 0.0
    if "SPY" in ohlcv and n > start:
        spy_pnl = (float(ohlcv["SPY"]["close"][n - 1]) - float(ohlcv["SPY"]["close"][start])) * 100

    wins = [t for t in trades if t.pnl > 0]
    total = sum(t.pnl for t in trades)
    return MomentumBacktestResult(
        symbols=syms,
        trade_count=len(trades),
        winners=len(wins),
        losers=len(trades) - len(wins),
        win_rate=len(wins) / len(trades) if trades else 0.0,
        total_pnl=round(total, 2),
        expectancy=round(total / len(trades), 2) if trades else 0.0,
        spy_buy_hold_pnl=round(spy_pnl, 2),
        beat_spy=total > spy_pnl,
        trades=trades,
        assumptions=list(ASSUMPTIONS),
        metadata={"period": period, "top_k": top_k, "n_bars": n, "slip_bps": slip_bps},
    )


def format_momentum_report(r: MomentumBacktestResult) -> str:
    lines = [
        "# Cross-sectional momentum / RS sleeve",
        "",
        "## Assumptions",
    ]
    for a in r.assumptions:
        lines.append(f"- {a}")
    lines += [
        "",
        f"**Trades:** {r.trade_count}  **WR:** {r.win_rate:.1%}  "
        f"**Exp:** ${r.expectancy:+.2f}  **Total:** ${r.total_pnl:+.2f}",
        f"**SPY buy-hold (100 sh):** ${r.spy_buy_hold_pnl:+.2f}  **Beat SPY:** {r.beat_spy}",
        f"Meta: {r.metadata}",
        "",
    ]
    return "\n".join(lines) + "\n"
