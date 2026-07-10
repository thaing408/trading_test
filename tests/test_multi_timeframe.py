"""Unit tests for multi-timeframe technical analysis."""

from trading_agent.analysis.technical import (
    compute_technical_analysis,
    resample_weekly,
    timeframe_alignment,
    trend_label,
)


def _uptrend_bars(n: int, start: float = 100.0):
    closes = [start + i * 2 for i in range(n)]
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    volumes = [1_000_000] * n
    return closes, highs, lows, volumes


def test_resample_weekly_aggregates():
    closes, highs, lows, volumes = _uptrend_bars(30)
    w_c, w_h, w_l, w_v = resample_weekly(closes, highs, lows, volumes)
    assert len(w_c) == 6
    assert w_c[-1] > w_c[0]


def test_timeframe_alignment_bullish():
    trends = {"daily": "uptrend", "weekly": "uptrend", "intraday": "uptrend"}
    assert timeframe_alignment(trends) == "aligned_bullish"


def test_multi_timeframe_increases_score_when_aligned():
    daily = _uptrend_bars(60, 100)
    hourly = _uptrend_bars(35, 200)
    m30 = _uptrend_bars(40, 150)
    m15 = _uptrend_bars(40, 140)
    ta = compute_technical_analysis(
        "TEST",
        daily[0], daily[1], daily[2], daily[3],
        intraday_closes=hourly[0],
        intraday_highs=hourly[1],
        intraday_lows=hourly[2],
        intraday_volumes=hourly[3],
        bars_30m=m30[0],
        bars_15m=m15[0],
    )
    for key in ("monthly", "weekly", "daily", "4h", "1h", "30m", "15m"):
        assert key in ta.timeframe_trends
    assert "intraday" in ta.timeframe_trends
    assert ta.timeframe_alignment == "aligned_bullish"
    assert ta.score >= 60


def test_pipeline_uses_multiple_intervals(monkeypatch):
    from trading_agent.config import AgentConfig
    from trading_agent.pipeline import _get_ohlcv

    calls = []

    def fake_ohlcv(symbol, config, interval="1d", period="3mo"):
        calls.append(interval)
        return {"close": [100, 101, 102], "high": [101, 102, 103], "low": [99, 100, 101], "volume": [1, 1, 1]}

    monkeypatch.setattr("trading_agent.pipeline._get_ohlcv", fake_ohlcv)
    from trading_agent.pipeline import _analyze_candidate
    from trading_agent.models import ScreenerCandidate

    c = ScreenerCandidate("X", 100, 1_000_000, 1.5, 80, 5000, 1.0)
    _analyze_candidate(c, AgentConfig(fixture_mode=False), [100, 101, 102])
    assert "1d" in calls
    assert "1h" in calls