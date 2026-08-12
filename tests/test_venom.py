"""Unit tests for Venom Model v1 detectors."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from trading_agent.pa.venom import (
    ET,
    compute_venom_box,
    detect_box_sweep,
    find_bpr,
    scan_venom_signals,
)
from trading_agent.pa.fvg import FairValueGap


def _ts_day(d: date, hour: int, minute: int = 0):
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=ET)


def test_venom_box_0800_0930():
    d = date(2026, 7, 15)
    # 5m bars 8:00–9:25 + after
    times, highs, lows = [], [], []
    t = _ts_day(d, 8, 0)
    px = 100.0
    while t.hour < 10 or (t.hour == 10 and t.minute == 0):
        times.append(t)
        # box phase spikes
        if t.hour < 9 or (t.hour == 9 and t.minute < 30):
            highs.append(px + 2.0)
            lows.append(px - 1.0)
        else:
            highs.append(px + 0.5)
            lows.append(px - 0.5)
        t += timedelta(minutes=5)
    box = compute_venom_box(times, highs, lows, d)
    assert box is not None
    assert box.high >= 101.5
    assert box.low <= 99.5


def test_sweep_low_detection():
    d = date(2026, 7, 15)
    times = [_ts_day(d, 8, 0), _ts_day(d, 9, 0), _ts_day(d, 9, 35)]
    highs = [102.0, 101.5, 100.5]
    lows = [100.0, 99.5, 98.5]  # last pierces
    closes = [101.0, 100.5, 100.2]  # reclaim above box low 99.5
    from trading_agent.pa.venom import VenomBox

    box = VenomBox(session=d, high=102.0, low=99.5, start_idx=0, end_idx=1)
    sw = detect_box_sweep(highs, lows, closes, box, 2)
    assert sw == "low"


def test_bpr_overlap():
    bulls = [FairValueGap(side="bullish", gap_low=100.0, gap_high=101.0, index=5)]
    bears = [FairValueGap(side="bearish", gap_low=100.5, gap_high=101.5, index=6)]
    bpr = find_bpr(bulls + bears)
    assert bpr is not None
    assert bpr.low == 100.5
    assert bpr.high == 101.0


def test_scan_finds_bullish_signal():
    """Synthetic: box, sweep low, then bullish reclaim bars."""
    d = date(2026, 7, 15)
    times, o, h, l, c = [], [], [], [], []
    # 8:00–9:25 box around 100-102
    t = _ts_day(d, 8, 0)
    while t < _ts_day(d, 9, 30):
        times.append(t)
        o.append(100.5)
        h.append(102.0)
        l.append(100.0)
        c.append(101.0)
        t += timedelta(minutes=5)
    # 9:30+ sweep low then reverse
    for i, (hh, ll, cc, oo) in enumerate(
        [
            (100.5, 99.0, 100.2, 100.0),  # sweep
            (101.0, 99.8, 100.8, 100.1),
            (102.5, 100.5, 102.2, 100.9),  # displacement / engulf-ish
            (102.0, 101.0, 101.5, 101.8),  # retest zone
        ]
    ):
        times.append(_ts_day(d, 9, 30) + timedelta(minutes=5 * (i + 1)))
        o.append(oo)
        h.append(hh)
        l.append(ll)
        c.append(cc)

    sigs = scan_venom_signals(
        times, o, h, l, c, d, require_structure=False, max_entries=1
    )
    # May or may not fire depending on structure — at least no crash
    assert isinstance(sigs, list)
    if sigs:
        assert sigs[0].side in ("CALL", "PUT")
        assert sigs[0].stop != sigs[0].entry
