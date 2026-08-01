"""Orchestrate historical load → walk-forward desk BT → feature ML compare."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, Optional, Sequence

from trading_agent.backtest.engine import default_sweep_configs
from trading_agent.backtest.historical import load_historical_ohlcv, ohlcv_provenance
from trading_agent.backtest.walk_forward import (
    format_walk_forward_report,
    run_walk_forward,
)
from trading_agent.ml.ranker import format_ranker_report, train_ranker_walk_forward


def run_quant_research(
    *,
    historical: bool = True,
    period: str = "1y",
    symbols: Optional[Sequence[str]] = None,
    train_bars: int = 80,
    test_bars: int = 20,
    step_bars: int = 20,
    embargo_bars: int = 5,
    slippage_bps: float = 5.0,
    commission: float = 1.0,
    include_ml: bool = True,
    allow_synthetic_fallback: bool = True,
) -> Dict[str, Any]:
    """Full research pack: data → WF desk path → optional ML vs baseline."""
    if historical:
        ohlcv = load_historical_ohlcv(
            symbols,
            period=period,
            allow_synthetic_fallback=allow_synthetic_fallback,
        )
    else:
        from trading_agent.backtest.data import default_backtest_universe

        ohlcv = default_backtest_universe()
        for s in ohlcv:
            ohlcv[s]["source"] = "synthetic"

    base = default_sweep_configs()[0]
    cfg = replace(
        base,
        name=f"{base.name}_wf",
        slippage_bps=slippage_bps,
        commission_per_trade=commission,
        use_historical_ohlcv=bool(historical),
    )

    wf = run_walk_forward(
        cfg,
        ohlcv,
        symbols=list(ohlcv.keys()),
        train_bars=train_bars,
        test_bars=test_bars,
        step_bars=step_bars,
        embargo_bars=embargo_bars,
    )

    ml_summary = None
    if include_ml:
        ml_summary = train_ranker_walk_forward(
            ohlcv,
            train_bars=train_bars,
            test_bars=test_bars,
            step_bars=step_bars,
            embargo=embargo_bars,
        )

    return {
        "provenance": ohlcv_provenance(ohlcv),
        "n_symbols": len(ohlcv),
        "walk_forward": wf.to_dict(),
        "walk_forward_text": format_walk_forward_report(wf),
        "ml": ml_summary,
        "ml_text": format_ranker_report(ml_summary) if ml_summary else "",
        "config": {
            "period": period,
            "historical": historical,
            "slippage_bps": slippage_bps,
            "commission": commission,
            "train_bars": train_bars,
            "test_bars": test_bars,
            "embargo_bars": embargo_bars,
        },
    }


def format_quant_research_report(pack: Dict[str, Any]) -> str:
    lines = [
        "# Quant research pack (historical + walk-forward + ML gate)",
        f"Config: {pack.get('config')}",
        f"Symbols: {pack.get('n_symbols')}  Provenance sample: "
        f"{list((pack.get('provenance') or {}).items())[:4]}",
        "",
        pack.get("walk_forward_text") or "",
        "",
        pack.get("ml_text") or "",
    ]
    return "\n".join(lines)
