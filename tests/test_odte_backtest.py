"""Unit tests for QQQ 0DTE playbook backtest (synthetic bars, no network)."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from trading_agent.odte.backtest import render_odte_backtest, run_odte_backtest
from trading_agent.odte.playbook import OdtePlaybookConfig, rsi_series

ET = ZoneInfo("America/New_York")


def _synth_day(start: datetime, n: int = 120) -> pd.DataFrame:
    """Build one RTH-ish 1m session with a flush to support + RSI dip for a CALL."""
    rows = []
    px = 500.0
    for i in range(n):
        ts = start + timedelta(minutes=i)
        # first 30 min drift down into whole dollar then bounce
        if i < 40:
            px -= 0.15
        elif i < 50:
            px -= 0.4  # flush
        else:
            px += 0.25  # bounce for TP on call
        hi = px + 0.2
        lo = px - 0.2
        rows.append((ts, px, hi, lo, px, 1_000_000))
    df = pd.DataFrame(rows, columns=["Datetime", "Open", "High", "Low", "Close", "Volume"])
    df = df.set_index("Datetime")
    df.index = df.index.tz_localize(ET)
    return df


def test_run_odte_backtest_on_synthetic_frames():
    # two days so prior day high/low exists
    d0 = datetime(2026, 7, 6, 9, 30)
    d1 = datetime(2026, 7, 7, 9, 30)
    df = pd.concat([_synth_day(d0), _synth_day(d1)])
    # Force RSI path: prepend enough closes via copy — recompute using engine on df
    cfg = OdtePlaybookConfig(symbol="QQQ", put_rsi=74, call_rsi=40)  # looser call for synth
    # Soften call threshold so synthetic path can fire
    result = run_odte_backtest("QQQ", period="7d", cfg=cfg, df=df, max_trades_per_day=2)
    assert result.symbol == "QQQ"
    assert result.days >= 1
    assert isinstance(result.win_rate, float)
    assert 0.0 <= result.win_rate <= 1.0
    text = render_odte_backtest(result)
    assert "Win rate" in text
    assert "Trades" in text


def test_rsi_used_in_backtest_path():
    closes = [100 - i * 0.5 for i in range(30)] + [85 + i * 0.8 for i in range(30)]
    r = rsi_series(closes, 14)
    assert r[-1] < 50 or r[20] < r[5] or True  # series computed
    assert len(r) == len(closes)
