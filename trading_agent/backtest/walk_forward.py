"""Walk-forward evaluation on the desk decision path (G3.3).

Splits bar history into rolling train / test windows. For each fold:
- **Train segment**: metrics only (optional ML fit hook)
- **Test segment**: run ``run_backtest`` restricted to that bar range

Purged gap (embargo) between train and test reduces leakage (G3.4 light).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from trading_agent.backtest.engine import run_backtest, score_period
from trading_agent.backtest.models import BacktestConfig, BacktestPeriodResult


def _copy_cfg(cfg: BacktestConfig, name: str) -> BacktestConfig:
    d = asdict(cfg)
    d["name"] = name
    return BacktestConfig(**d)


@dataclass
class WalkForwardWindow:
    fold: int
    train_start: int
    train_end: int  # exclusive
    test_start: int
    test_end: int  # exclusive
    embargo: int = 0


@dataclass
class WalkForwardFoldResult:
    fold: int
    window: WalkForwardWindow
    train_bars: int
    test_bars: int
    test_result: Optional[BacktestPeriodResult] = None
    train_result: Optional[BacktestPeriodResult] = None
    ml_metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "fold": self.fold,
            "train_start": self.window.train_start,
            "train_end": self.window.train_end,
            "test_start": self.window.test_start,
            "test_end": self.window.test_end,
            "train_bars": self.train_bars,
            "test_bars": self.test_bars,
            "ml_metrics": self.ml_metrics,
        }
        if self.test_result:
            d["test"] = {
                "trade_count": self.test_result.trade_count,
                "expectancy": self.test_result.expectancy,
                "win_rate": self.test_result.win_rate,
                "total_pnl": self.test_result.total_pnl,
                "max_drawdown": self.test_result.max_drawdown,
                "profit_factor": self.test_result.profit_factor,
                "score": score_period(self.test_result),
            }
        if self.train_result:
            d["train"] = {
                "trade_count": self.train_result.trade_count,
                "expectancy": self.train_result.expectancy,
                "win_rate": self.train_result.win_rate,
                "score": score_period(self.train_result),
            }
        return d


@dataclass
class WalkForwardReport:
    config_name: str
    n_bars: int
    folds: List[WalkForwardFoldResult] = field(default_factory=list)
    aggregate: Dict[str, Any] = field(default_factory=dict)
    data_source: str = ""
    symbols: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "config_name": self.config_name,
            "n_bars": self.n_bars,
            "data_source": self.data_source,
            "symbols": self.symbols,
            "aggregate": self.aggregate,
            "folds": [f.to_dict() for f in self.folds],
        }


def make_walk_forward_windows(
    n_bars: int,
    *,
    train_bars: int = 80,
    test_bars: int = 20,
    step_bars: int = 20,
    embargo_bars: int = 5,
    min_start: int = 40,
) -> List[WalkForwardWindow]:
    """Expanding or rolling: fixed train length ending before embargo+test."""
    windows: List[WalkForwardWindow] = []
    fold = 0
    # First test starts after min_start + train
    test_start = max(min_start + train_bars + embargo_bars, train_bars + embargo_bars)
    while test_start + test_bars <= n_bars:
        train_end = test_start - embargo_bars
        train_start = max(min_start, train_end - train_bars)
        if train_end - train_start < max(20, train_bars // 2):
            test_start += step_bars
            continue
        windows.append(
            WalkForwardWindow(
                fold=fold,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_start + test_bars,
                embargo=embargo_bars,
            )
        )
        fold += 1
        test_start += step_bars
    return windows


def _slice_ohlcv(ohlcv: Dict[str, dict], start: int, end: int) -> Dict[str, dict]:
    """Slice bars [start, end) for each symbol (re-index 0..n-1)."""
    out: Dict[str, dict] = {}
    for sym, pack in ohlcv.items():
        closes = list(pack.get("close") or [])
        if end > len(closes):
            end_i = len(closes)
        else:
            end_i = end
        start_i = max(0, min(start, end_i))
        if end_i - start_i < 10:
            continue
        sliced = {
            "close": closes[start_i:end_i],
            "high": list(pack.get("high") or closes)[start_i:end_i],
            "low": list(pack.get("low") or closes)[start_i:end_i],
            "volume": list(pack.get("volume") or [1e6] * len(closes))[start_i:end_i],
            "source": pack.get("source"),
        }
        if pack.get("open"):
            sliced["open"] = list(pack["open"])[start_i:end_i]
        for k in ("iv", "iv_history"):
            if k in pack:
                sliced[k] = pack[k]
        out[sym] = sliced
    return out


def run_walk_forward(
    cfg: BacktestConfig,
    ohlcv: Dict[str, dict],
    *,
    symbols: Optional[Sequence[str]] = None,
    train_bars: int = 80,
    test_bars: int = 20,
    step_bars: int = 20,
    embargo_bars: int = 5,
    run_train_segment: bool = False,
    on_fold_train: Optional[Callable[[WalkForwardWindow, Dict[str, dict]], Dict[str, Any]]] = None,
) -> WalkForwardReport:
    """Walk-forward desk backtest on provided OHLCV."""
    preferred = list(symbols) if symbols else list(ohlcv.keys())
    syms = [s for s in preferred if s in ohlcv]
    if not syms:
        syms = list(ohlcv.keys())
    n_bars = min(len(ohlcv[s]["close"]) for s in syms) if syms else 0
    min_start = max(cfg.lookback_bars, 20)

    windows = make_walk_forward_windows(
        n_bars,
        train_bars=train_bars,
        test_bars=test_bars,
        step_bars=step_bars,
        embargo_bars=embargo_bars,
        min_start=min_start,
    )

    folds: List[WalkForwardFoldResult] = []
    sources = {str(ohlcv[s].get("source") or "") for s in syms}
    data_source = ",".join(sorted(sources)) if sources else "unknown"

    # Include lookback history before each segment so technicals/ranker have bars
    lb = max(int(cfg.lookback_bars), 20)

    for win in windows:
        train_slice = _slice_ohlcv(
            ohlcv, max(0, win.train_start - lb), win.train_end
        )
        # Test slice starts lb bars before test_start so day loop can fire in-window
        test_slice = _slice_ohlcv(
            ohlcv, max(0, win.test_start - lb), win.test_end
        )
        ml_metrics: Dict[str, Any] = {}
        if on_fold_train is not None:
            try:
                ml_metrics = on_fold_train(win, train_slice) or {}
            except Exception as exc:
                ml_metrics = {"error": str(exc)}

        train_result = None
        if run_train_segment and train_slice:
            tcfg = _copy_cfg(cfg, f"{cfg.name}_train_f{win.fold}")
            train_result = run_backtest(tcfg, ohlcv=train_slice, symbols=syms)

        test_result = None
        if test_slice:
            tcfg = _copy_cfg(cfg, f"{cfg.name}_test_f{win.fold}")
            test_result = run_backtest(tcfg, ohlcv=test_slice, symbols=syms)

        folds.append(
            WalkForwardFoldResult(
                fold=win.fold,
                window=win,
                train_bars=win.train_end - win.train_start,
                test_bars=win.test_end - win.test_start,
                test_result=test_result,
                train_result=train_result,
                ml_metrics=ml_metrics,
            )
        )

    # Aggregate OOS
    exp = [f.test_result.expectancy for f in folds if f.test_result and f.test_result.trade_count]
    wr = [f.test_result.win_rate for f in folds if f.test_result and f.test_result.trade_count]
    pnl = [f.test_result.total_pnl for f in folds if f.test_result]
    n_tr = [f.test_result.trade_count for f in folds if f.test_result]
    scores = [score_period(f.test_result) for f in folds if f.test_result]

    aggregate = {
        "folds": len(folds),
        "folds_with_trades": sum(1 for n in n_tr if n > 0),
        "oos_total_pnl": round(sum(pnl), 2) if pnl else 0.0,
        "oos_mean_expectancy": round(sum(exp) / len(exp), 2) if exp else 0.0,
        "oos_mean_win_rate": round(sum(wr) / len(wr), 4) if wr else 0.0,
        "oos_total_trades": int(sum(n_tr)) if n_tr else 0,
        "oos_mean_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
    }

    return WalkForwardReport(
        config_name=cfg.name,
        n_bars=n_bars,
        folds=folds,
        aggregate=aggregate,
        data_source=data_source,
        symbols=list(syms),
    )


def format_walk_forward_report(report: WalkForwardReport) -> str:
    lines = [
        f"# Walk-forward — {report.config_name}",
        f"Bars: {report.n_bars}  Source: {report.data_source}",
        f"Symbols: {', '.join(report.symbols)}",
        "",
        "## OOS aggregate",
    ]
    for k, v in report.aggregate.items():
        lines.append(f"- **{k}:** {v}")
    lines.append("")
    lines.append("## Folds")
    for f in report.folds:
        tr = f.test_result
        if not tr:
            lines.append(f"- fold {f.fold}: no test result")
            continue
        lines.append(
            f"- fold {f.fold} bars[{f.window.test_start}:{f.window.test_end}] "
            f"n={tr.trade_count} exp=${tr.expectancy:+.2f} WR={tr.win_rate:.0%} "
            f"P/L=${tr.total_pnl:+.2f} DD=${tr.max_drawdown:,.0f} "
            f"score={score_period(tr):.1f}"
        )
        if f.ml_metrics:
            lines.append(f"  ml: {f.ml_metrics}")
    if not report.folds:
        lines.append("- _No walk-forward windows (need longer history)._")
    return "\n".join(lines) + "\n"
