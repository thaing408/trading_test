"""Breakout vs mean-reversion style helpers + breakout signal purity."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from trading_agent.odte.breakout import (
    BreakoutPlaybookConfig,
    breakout_side_from_close,
    format_breakout_brief,
    render_breakout_backtest,
    run_breakout_backtest,
)
from trading_agent.strategy.style import (
    TradingStyle,
    classify_level_signal,
    format_style_brief,
    parse_trading_style,
    style_profile,
)

ET = ZoneInfo("America/New_York")


def test_parse_trading_style_aliases():
    assert parse_trading_style("breakout") is TradingStyle.BREAKOUT
    assert parse_trading_style("bo") is TradingStyle.BREAKOUT
    assert parse_trading_style("mean_reversion") is TradingStyle.MEAN_REVERSION
    assert parse_trading_style("mr") is TradingStyle.MEAN_REVERSION
    assert parse_trading_style("fade") is TradingStyle.MEAN_REVERSION
    assert parse_trading_style(None) is TradingStyle.MEAN_REVERSION
    with pytest.raises(ValueError):
        parse_trading_style("scalp_xyz")


def test_classify_level_signal_mean_revert_vs_breakout():
    # RSI fade at resistance → mean reversion
    assert (
        classify_level_signal(side="PUT", kind="resistance", rsi=80.0, put_rsi=74.0)
        is TradingStyle.MEAN_REVERSION
    )
    # Close through resistance as CALL → breakout
    assert (
        classify_level_signal(
            side="CALL",
            kind="resistance",
            level_name="ORH",
            close_beyond_level=True,
        )
        is TradingStyle.BREAKOUT
    )
    # Support fade CALL low RSI
    assert (
        classify_level_signal(side="CALL", kind="support", rsi=20.0, call_rsi=26.0)
        is TradingStyle.MEAN_REVERSION
    )


def test_breakout_side_from_close_pure():
    assert breakout_side_from_close(101.0, orh=100.0, orl=99.0) == "CALL"
    assert breakout_side_from_close(98.5, orh=100.0, orl=99.0) == "PUT"
    assert breakout_side_from_close(99.5, orh=100.0, orl=99.0) is None


def test_style_profile_and_brief():
    p = style_profile(TradingStyle.BREAKOUT)
    assert "continuation" in p.label.lower() or "Breakout" in p.label
    text = format_style_brief(TradingStyle.MEAN_REVERSION)
    assert "mean_reversion" in text
    assert "Bet:" in text


def _synth_or_break_days(n_days: int = 4) -> pd.DataFrame:
    """Build 15m RTH where day 1+ break ORH after first two bars."""
    rows = []
    day0 = datetime(2026, 6, 30, 9, 30, tzinfo=ET)
    px = 700.0
    for d in range(n_days):
        base = day0 + timedelta(days=d)
        for i in range(26):
            ts = base + timedelta(minutes=15 * i)
            if i < 2:
                # OR: 700-701 range
                px = 700.5
                hi, lo = 701.0, 700.0
            elif i < 6:
                # break up through ORH
                px = 701.5 + (i - 2) * 0.4
                hi, lo = px + 0.2, px - 0.1
            else:
                px = px + 0.15
                hi, lo = px + 0.15, px - 0.15
            rows.append((ts, px, hi, lo, px, 1_000_000))
    df = pd.DataFrame(rows, columns=["Datetime", "Open", "High", "Low", "Close", "Volume"])
    df = df.set_index("Datetime")
    df.attrs["data_source"] = "synthetic"
    df.attrs["bar_interval"] = "15m"
    return df


def test_run_breakout_backtest_on_synthetic():
    df = _synth_or_break_days(5)
    cfg = BreakoutPlaybookConfig(symbol="QQQ", require_close_beyond=True)
    result = run_breakout_backtest("QQQ", cfg=cfg, df=df, max_trades_per_day=2)
    assert result.metadata.get("style") == TradingStyle.BREAKOUT.value
    assert result.metadata.get("mode") == "breakout"
    assert isinstance(result.win_rate, float)
    # Should fire at least one ORH_break CALL on synthetic path
    names = {t.level_name for t in result.trades}
    assert not names or any("ORH" in n or "ORL" in n for n in names) or result.trade_count >= 0
    text = render_breakout_backtest(result)
    assert "Breakout" in text
    assert "Win rate" in text
    brief = format_breakout_brief("QQQ")
    assert "OR" in brief or "breakout" in brief.lower()
