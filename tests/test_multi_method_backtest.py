"""Offline test for multi-method router historical backtest."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from trading_agent.strategy.multi_method_backtest import (
    RouterBacktestConfig,
    render_multi_method_backtest,
    run_multi_method_backtest,
)

ET = ZoneInfo("America/New_York")


def _multi_day_df(seed: int = 1, days: int = 8) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    idx = []
    px = 100.0 + seed
    start = datetime(2026, 6, 2, 9, 30, tzinfo=ET)  # Monday
    for d in range(days):
        # skip weekends roughly by adding days
        day0 = start + timedelta(days=d)
        if day0.weekday() >= 5:
            continue
        for b in range(26):  # 9:30-16:00 15m
            ts = day0 + timedelta(minutes=15 * b)
            px = px + rng.normal(0.02, 0.2)
            o, c = px, px + rng.normal(0, 0.1)
            h, l = max(o, c) + 0.4, min(o, c) - 0.4
            rows.append({"Open": o, "High": h, "Low": l, "Close": c, "Volume": 5000})
            idx.append(ts)
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx))


def test_router_backtest_offline(monkeypatch):
    frames = {
        "AAA": _multi_day_df(1),
        "BBB": _multi_day_df(2),
    }

    def fake_fetch(symbol, *, period, interval, source):
        return frames[symbol]

    monkeypatch.setattr(
        "trading_agent.strategy.multi_method_backtest.fetch_bars",
        fake_fetch,
    )
    from trading_agent.strategy.multi_method import MultiMethodConfig

    result = run_multi_method_backtest(
        ["AAA", "BBB"],
        period="10d",
        interval="15m",
        data_source="yfinance",
        router_cfg=MultiMethodConfig(
            min_method_score=40,
            min_play_methods=1,
            use_htf_bias=False,
        ),
        bt_cfg=RouterBacktestConfig(max_trades_per_day=1, min_method_score=40),
    )
    assert result.symbol == "MULTI_METHOD_ROUTER"
    assert result.days >= 1
    assert "pct_days_with_play" in (result.metadata or {})
    text = render_multi_method_backtest(result)
    assert "Multi-Method Router" in text
    assert "Daily hit rate" in text
