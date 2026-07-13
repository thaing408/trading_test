"""Offline multi-day backtests of research + CIO decision chain."""

from trading_agent.backtest.engine import run_backtest, run_config_sweep
from trading_agent.backtest.models import BacktestConfig, BacktestPeriodResult, DayResult
from trading_agent.backtest.report import render_comparison, render_period_report

__all__ = [
    "BacktestConfig",
    "BacktestPeriodResult",
    "DayResult",
    "run_backtest",
    "run_config_sweep",
    "render_comparison",
    "render_period_report",
]
