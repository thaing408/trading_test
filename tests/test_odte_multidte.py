"""Tests for multi-DTE HTF playbook (synthetic bars, no network)."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from trading_agent.odte.multidte import (
    MultidtePlaybookConfig,
    format_multidte_brief,
    next_friday_dte,
    recommend_expiration_label,
    render_multidte_backtest,
    run_multidte_backtest,
)

ET = ZoneInfo("America/New_York")


def _synth_15m_days(n_days: int = 5, bars_per_day: int = 26) -> pd.DataFrame:
    """Rough RTH 15m bars: open 9:30, ~26 bars to 16:00."""
    rows = []
    # start on a Monday
    day0 = datetime(2026, 6, 29, 9, 30, tzinfo=ET)
    px = 700.0
    for d in range(n_days):
        base = day0 + timedelta(days=d)
        for i in range(bars_per_day):
            ts = base + timedelta(minutes=15 * i)
            # mild trend + mean reversion for level touches
            if i < 8:
                px -= 0.35
            elif i < 14:
                px += 0.55
            else:
                px += 0.1 * (1 if d % 2 == 0 else -1)
            hi = px + 0.4
            lo = px - 0.4
            rows.append((ts, px, hi, lo, px, 1_000_000))
    df = pd.DataFrame(rows, columns=["Datetime", "Open", "High", "Low", "Close", "Volume"])
    df = df.set_index("Datetime")
    df.attrs["data_source"] = "synthetic"
    df.attrs["bar_interval"] = "15m"
    return df


def test_next_friday_dte_positive():
    # a known Wednesday
    d = datetime(2026, 7, 8).date()  # Wednesday
    assert next_friday_dte(d) == 2
    assert recommend_expiration_label(3, d) == "2026-07-11"


def test_run_multidte_backtest_synthetic():
    df = _synth_15m_days(6)
    cfg = MultidtePlaybookConfig(
        symbol="QQQ",
        target_dte=5,
        bar_interval="15m",
        put_rsi=55,
        call_rsi=45,
        require_rejection_close=False,
        puts_only=False,
    )
    result = run_multidte_backtest("QQQ", period="60d", cfg=cfg, df=df)
    assert result.symbol == "QQQ"
    assert result.metadata.get("mode") == "multidte"
    assert result.metadata.get("target_dte") == 5
    assert 0.0 <= result.win_rate <= 1.0
    text = render_multidte_backtest(result)
    assert "Multi-DTE" in text
    assert "Win rate" in text


def test_puts_only_filters_calls():
    df = _synth_15m_days(6)
    cfg = MultidtePlaybookConfig(
        symbol="QQQ",
        put_rsi=50,
        call_rsi=50,
        require_rejection_close=False,
        puts_only=True,
    )
    result = run_multidte_backtest("QQQ", cfg=cfg, df=df, max_trades_per_day=5)
    for t in result.trades:
        assert t.side == "PUT", t


def test_format_multidte_brief():
    text = format_multidte_brief("QQQ", last=710.5, rsi_htf=62.0)
    assert "Multi-DTE" in text
    assert "QQQ" in text
    assert "710.5" in text or "710" in text
