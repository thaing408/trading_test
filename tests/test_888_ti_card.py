"""888 TI visual decision card — simple LONG/SHORT/WAIT."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd

from trading_agent.odte.breakout import (
    BreakoutPlaybookConfig,
    BreakoutSnapshot,
    breakout_side_from_close,
    compute_breakout_snapshot,
    format_888_ti_card,
    format_breakout_brief,
)

ET = ZoneInfo("America/New_York")


def _or_day_df(*, orh: float, orl: float, last: float, day="2026-08-03"):
    """Two 15m OR bars + one signal bar (synthetic)."""
    idx = pd.date_range(f"{day} 09:30", periods=4, freq="15min", tz=ET)
    # bar0-1 = OR, bar2-3 = after
    high = [orh, orh - 0.1, max(orh, last), max(orh, last)]
    low = [orl + 0.1, orl, min(orl, last), min(orl, last)]
    close = [orl + 0.5, (orh + orl) / 2, last, last]
    open_ = close[:]
    df = pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": [1e6] * 4},
        index=idx,
    )
    df.attrs["data_source"] = "synthetic"
    df.attrs["bar_interval"] = "15m"
    return df


def test_breakout_side_from_close():
    assert breakout_side_from_close(101, 100, 99) == "CALL"
    assert breakout_side_from_close(98, 100, 99) == "PUT"
    assert breakout_side_from_close(99.5, 100, 99) is None


def test_card_long_visual():
    df = _or_day_df(orh=100.0, orl=98.0, last=101.5)
    now = datetime(2026, 8, 3, 11, 0, tzinfo=ET)
    snap = compute_breakout_snapshot(
        "QQQ",
        cfg=BreakoutPlaybookConfig(symbol="QQQ", bar_interval="15m", or_minutes=30),
        df=df,
        now_et=now,
    )
    assert snap.decision == "LONG"
    assert snap.orh == 100.0
    text = format_888_ti_card(snap)
    assert "888 TI" in text
    assert "LONG" in text
    assert "DECISION" in text
    assert "101.50" in text or "101.5" in text


def test_card_wait_inside_box():
    df = _or_day_df(orh=100.0, orl=98.0, last=99.0)
    now = datetime(2026, 8, 3, 11, 0, tzinfo=ET)
    snap = compute_breakout_snapshot(
        "QQQ",
        cfg=BreakoutPlaybookConfig(symbol="QQQ", bar_interval="15m", or_minutes=30),
        df=df,
        now_et=now,
    )
    assert snap.decision == "WAIT"
    text = format_888_ti_card(snap)
    assert "WAIT" in text
    assert "NO TRADE" in text


def test_card_short():
    df = _or_day_df(orh=100.0, orl=98.0, last=97.0)
    now = datetime(2026, 8, 3, 11, 0, tzinfo=ET)
    snap = compute_breakout_snapshot(
        "SPY",
        cfg=BreakoutPlaybookConfig(symbol="SPY", bar_interval="15m", or_minutes=30),
        df=df,
        now_et=now,
    )
    assert snap.decision == "SHORT"
    text = format_888_ti_card(snap)
    assert "SHORT" in text


def test_static_brief_no_network():
    text = format_breakout_brief("QQQ", live=False)
    assert "888 TI" in text
    assert "DECISION" in text
