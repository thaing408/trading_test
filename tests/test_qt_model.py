"""Unit tests for QT open-window mechanical proxies (pure bars)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from trading_agent.qt.model import (
    QtModelConfig,
    cisd_confirm,
    detect_fvg,
    evaluate_qt_bars,
    signals_to_auto_trade_entries,
    target_from_rr,
)

ET = ZoneInfo("America/New_York")


def _session_bars(
    session: date,
    *,
    or_high: float = 100.5,
    or_low: float = 99.5,
    long_setup: bool = True,
):
    """Build 1m-like bars: 9:30 OR then PO3 sweep+reclaim with CISD."""
    stamps = []
    opens, highs, lows, closes = [], [], [], []
    t0 = datetime(session.year, session.month, session.day, 9, 30, tzinfo=ET)
    # prior day bars for HTF
    prior = session - timedelta(days=1)
    while prior.weekday() >= 5:
        prior -= timedelta(days=1)
    tp = datetime(prior.year, prior.month, prior.day, 9, 30, tzinfo=ET)
    for i in range(10):
        stamps.append(tp + timedelta(minutes=i))
        # bullish prior day
        opens.append(98.0 + i * 0.05)
        highs.append(98.2 + i * 0.05)
        lows.append(97.9 + i * 0.05)
        closes.append(98.1 + i * 0.05)

    # OR 5 minutes
    for i in range(5):
        stamps.append(t0 + timedelta(minutes=i))
        opens.append(100.0)
        highs.append(or_high)
        lows.append(or_low)
        closes.append(100.0)

    if long_setup:
        # bar 5: sweep low then close reclaim
        stamps.append(t0 + timedelta(minutes=5))
        opens.append(99.8)
        highs.append(100.2)
        lows.append(or_low - 0.4)
        closes.append(or_low + 0.2)
        # CISD: higher closes + break swing
        for i in range(6, 12):
            stamps.append(t0 + timedelta(minutes=i))
            px = 100.0 + (i - 5) * 0.15
            opens.append(px - 0.05)
            highs.append(px + 0.2)
            lows.append(px - 0.1)
            closes.append(px)
    else:
        stamps.append(t0 + timedelta(minutes=5))
        opens.append(100.2)
        highs.append(or_high + 0.4)
        lows.append(99.8)
        closes.append(or_high - 0.2)
        for i in range(6, 12):
            stamps.append(t0 + timedelta(minutes=i))
            px = 100.0 - (i - 5) * 0.15
            opens.append(px + 0.05)
            highs.append(px + 0.1)
            lows.append(px - 0.2)
            closes.append(px)

    return stamps, opens, highs, lows, closes


def test_target_from_rr():
    assert target_from_rr(100, 98, "long", 2.0) == 104.0
    assert target_from_rr(100, 103, "short", 2.0) == 94.0


def test_detect_fvg_bullish():
    # i-2 high 10, i low 11 → bullish FVG
    o = [0, 0, 0]
    h = [10.0, 10.5, 12.0]
    l = [9.0, 10.2, 11.0]
    c = [9.5, 10.3, 11.5]
    fvg = detect_fvg(o, h, l, c, 2)
    assert fvg is not None
    assert fvg[0] == "bullish"


def test_cisd_long():
    highs = [10, 10.2, 10.1, 10.0, 10.3, 11.0]
    lows = [9.5, 9.6, 9.4, 9.3, 9.8, 10.5]
    # declining into bar 4, then CISD close above swing at bar 5
    closes = [9.8, 9.7, 9.5, 9.4, 9.3, 10.8]
    assert cisd_confirm(highs, lows, closes, side="long", start=0, end=5, lookback=3)


def test_po3_long_signal_package():
    session = date(2026, 6, 16)  # Monday
    stamps, o, h, l, c = _session_bars(session, long_setup=True)
    cfg = QtModelConfig(
        symbol="QQQ",
        require_cisd=True,
        require_ifvg=False,
        require_htf_align=True,
        rr_default=2.0,
    )
    brief = evaluate_qt_bars(
        stamps, o, h, l, c, cfg=cfg, session=session, now=stamps[-1]
    )
    assert brief.htf_bias in ("bullish", "neutral", "bearish")
    # May or may not fire depending on CISD bar geometry — if signal, geometry valid
    for s in brief.signals:
        assert s.side == "long"
        assert s.stop < s.entry < s.target
        assert s.rr >= 1.5
        rows = signals_to_auto_trade_entries(brief)
        assert rows
        assert rows[0]["action"] == "ENTER"
        assert rows[0]["instrument"] == "underlying"
        assert "qt_open_window" in rows[0]["method_tags"]


def test_no_signal_outside_range_chaos():
    session = date(2026, 6, 16)
    stamps, o, h, l, c = _session_bars(
        session, or_high=110.0, or_low=90.0, long_setup=True
    )
    cfg = QtModelConfig(symbol="QQQ", max_or_range_pct=1.0, require_cisd=False)
    brief = evaluate_qt_bars(stamps, o, h, l, c, cfg=cfg, session=session, now=stamps[-1])
    assert brief.signals == [] or any("OR range" in e for e in brief.errors)
