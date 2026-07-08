"""Unit tests for technical analysis indicators."""

from trading_agent.analysis.technical import (
    adx,
    atr,
    bollinger_position,
    compute_technical_analysis,
    macd_signal,
    ma_alignment,
    relative_strength,
    rsi,
    sma,
    trend_label,
)


def _sample_ohlcv():
    closes = [100 + i * 0.5 for i in range(60)]
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    volumes = [1_000_000 + i * 1000 for i in range(60)]
    return closes, highs, lows, volumes


def test_rsi_uptrend_above_50():
    closes, _, _, _ = _sample_ohlcv()
    assert rsi(closes) > 50


def test_sma_returns_average():
    assert sma([10, 20, 30, 40, 50], 5) == 30.0


def test_trend_label_uptrend():
    closes = [100 + i for i in range(20)]
    assert trend_label(closes) == "uptrend"


def test_macd_signal_bullish_on_rising():
    closes = [100 + i * 2 for i in range(40)]
    assert macd_signal(closes) == "bullish"


def test_atr_positive():
    closes, highs, lows, _ = _sample_ohlcv()
    assert atr(highs, lows, closes) > 0


def test_adx_computed():
    closes, highs, lows, _ = _sample_ohlcv()
    assert adx(highs, lows, closes) > 0


def test_bollinger_position():
    closes = [100.0] * 19 + [110.0]
    assert bollinger_position(closes) == "upper"


def test_ma_alignment_bullish():
    closes = [100 + i for i in range(60)]
    assert ma_alignment(closes) == "bullish"


def test_relative_strength_outperformer():
    sym = [100 + i for i in range(30)]
    bench = [100 + i * 0.5 for i in range(30)]
    assert relative_strength(sym, bench) > 0


def test_compute_technical_analysis_full():
    closes, highs, lows, volumes = _sample_ohlcv()
    ta = compute_technical_analysis("TEST", closes, highs, lows, volumes)
    assert ta.symbol == "TEST"
    assert 0 <= ta.score <= 100
    assert ta.support < ta.resistance