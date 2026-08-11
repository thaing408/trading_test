"""Multi-timeframe technical analysis (pure functions)."""

from __future__ import annotations

from typing import Dict, List, Sequence

import numpy as np

from trading_agent.analysis.patterns import detect_all_patterns, pattern_score_adjustment
from trading_agent.models import TechnicalAnalysis

# Canonical TF labels for Trading Research prompt
TIMEFRAME_ORDER = (
    "monthly",
    "weekly",
    "daily",
    "4h",
    "1h",
    "30m",
    "15m",
)


def sma(values: Sequence[float], period: int) -> float:
    if len(values) < period:
        return float(values[-1]) if values else 0.0
    return float(np.mean(values[-period:]))


def ema(values: Sequence[float], period: int) -> float:
    if not values:
        return 0.0
    alpha = 2 / (period + 1)
    result = float(values[0])
    for v in values[1:]:
        result = alpha * float(v) + (1 - alpha) * result
    return result


def rsi(closes: Sequence[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes[-(period + 1) :])
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = float(np.mean(gains)) or 1e-9
    avg_loss = float(np.mean(losses)) or 1e-9
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _ema_series(values: Sequence[float], period: int) -> List[float]:
    if not values:
        return []
    alpha = 2 / (period + 1)
    series = [float(values[0])]
    for v in values[1:]:
        series.append(alpha * float(v) + (1 - alpha) * series[-1])
    return series


def macd_signal(closes: Sequence[float]) -> str:
    if len(closes) < 26:
        return "neutral"
    ema12 = _ema_series(closes, 12)
    ema26 = _ema_series(closes, 26)
    macd_line = [a - b for a, b in zip(ema12, ema26)]
    signal_line = _ema_series(macd_line, 9)
    macd_val = macd_line[-1]
    signal_val = signal_line[-1]
    if macd_val > signal_val * 1.005:
        return "bullish"
    if macd_val < signal_val * 0.995:
        return "bearish"
    return "neutral"


def adx(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> float:
    if len(closes) < period + 2:
        return 20.0
    tr_list, plus_dm, minus_dm = [], [], []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        tr_list.append(tr)
        plus_dm.append(up if up > down and up > 0 else 0)
        minus_dm.append(down if down > up and down > 0 else 0)
    atr_val = float(np.mean(tr_list[-period:])) or 1e-9
    plus_di = 100 * float(np.mean(plus_dm[-period:])) / atr_val
    minus_di = 100 * float(np.mean(minus_dm[-period:])) / atr_val
    dx = abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9) * 100
    return round(dx, 2)


def atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> float:
    if len(closes) < 2:
        return 0.0
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    window = trs[-period:] if len(trs) >= period else trs
    return round(float(np.mean(window)), 4)


def bollinger_position(closes: Sequence[float], period: int = 20) -> str:
    if len(closes) < period:
        return "middle"
    window = closes[-period:]
    mid = float(np.mean(window))
    std = float(np.std(window)) or 1e-9
    last = float(closes[-1])
    if last > mid + std:
        return "upper"
    if last < mid - std:
        return "lower"
    return "middle"


def support_resistance(lows: Sequence[float], highs: Sequence[float]) -> tuple[float, float]:
    if not lows or not highs:
        return 0.0, 0.0
    return round(float(min(lows[-20:])), 2), round(float(max(highs[-20:])), 2)


def relative_strength(closes: Sequence[float], benchmark_closes: Sequence[float]) -> float:
    if len(closes) < 2 or len(benchmark_closes) < 2:
        return 0.0
    sym_ret = (closes[-1] - closes[0]) / closes[0]
    bench_ret = (benchmark_closes[-1] - benchmark_closes[0]) / benchmark_closes[0]
    return round((sym_ret - bench_ret) * 100, 2)


def vwap_relation(closes: Sequence[float], volumes: Sequence[float]) -> str:
    if not closes or not volumes or sum(volumes) == 0:
        return "at"
    vwap = sum(c * v for c, v in zip(closes, volumes)) / sum(volumes)
    last = closes[-1]
    if last > vwap * 1.005:
        return "above"
    if last < vwap * 0.995:
        return "below"
    return "at"


def ma_alignment(closes: Sequence[float]) -> str:
    if len(closes) < 50:
        return "mixed"
    e9, e20, e50 = ema(closes, 9), ema(closes, 20), ema(closes, 50)
    last = closes[-1]
    if last > e9 > e20 > e50:
        return "bullish"
    if last < e9 < e20 < e50:
        return "bearish"
    return "mixed"


def volume_profile_bias(volumes: Sequence[float]) -> str:
    if len(volumes) < 5:
        return "neutral"
    recent = float(np.mean(volumes[-3:]))
    prior = float(np.mean(volumes[-10:-3])) if len(volumes) >= 10 else recent
    if recent > prior * 1.2:
        return "accumulation"
    if recent < prior * 0.8:
        return "distribution"
    return "neutral"


def trend_label(closes: Sequence[float]) -> str:
    if len(closes) < 10:
        return "sideways"
    slope = (closes[-1] - closes[-10]) / closes[-10]
    if slope > 0.03:
        return "uptrend"
    if slope < -0.03:
        return "downtrend"
    return "sideways"


def breakout_state(closes: Sequence[float], highs: Sequence[float], lows: Sequence[float]) -> str:
    if len(closes) < 21:
        return "none"
    last = float(closes[-1])
    prior_high = float(max(highs[-21:-1]))
    prior_low = float(min(lows[-21:-1]))
    if last > prior_high * 1.002:
        return "breakout"
    if last < prior_low * 0.998:
        return "breakdown"
    return "none"


def momentum_label(closes: Sequence[float], rsi_val: float) -> str:
    if len(closes) < 5:
        return "neutral"
    roc = (closes[-1] - closes[-5]) / closes[-5] * 100
    if roc > 1.5 and rsi_val >= 55:
        return "bullish"
    if roc < -1.5 and rsi_val <= 45:
        return "bearish"
    return "neutral"


def resample_bars(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    volumes: Sequence[float],
    bars_per_period: int,
) -> tuple[List[float], List[float], List[float], List[float]]:
    """Aggregate bars into higher timeframe OHLCV."""
    if bars_per_period <= 1:
        return list(closes), list(highs), list(lows), list(volumes)
    w_close, w_high, w_low, w_vol = [], [], [], []
    for i in range(0, len(closes), bars_per_period):
        chunk_c = closes[i : i + bars_per_period]
        chunk_h = highs[i : i + bars_per_period]
        chunk_l = lows[i : i + bars_per_period]
        chunk_v = volumes[i : i + bars_per_period]
        if not chunk_c:
            continue
        w_close.append(float(chunk_c[-1]))
        w_high.append(float(max(chunk_h)))
        w_low.append(float(min(chunk_l)))
        w_vol.append(float(sum(chunk_v)))
    return w_close, w_high, w_low, w_vol


def resample_weekly(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    volumes: Sequence[float],
    bars_per_week: int = 5,
) -> tuple[List[float], List[float], List[float], List[float]]:
    """Aggregate daily bars into weekly OHLCV (testable without network)."""
    return resample_bars(closes, highs, lows, volumes, bars_per_week)


def timeframe_alignment(trends: Dict[str, str]) -> str:
    values = [t for t in trends.values() if t not in ("unavailable", "")]
    if not values:
        return "mixed"
    bullish = sum(1 for t in values if t == "uptrend")
    bearish = sum(1 for t in values if t == "downtrend")
    if bullish >= 3 and bearish == 0:
        return "aligned_bullish"
    if bearish >= 3 and bullish == 0:
        return "aligned_bearish"
    # Back-compat: 2+ aligned when fewer TFs present
    if bullish >= 2 and bearish == 0:
        return "aligned_bullish"
    if bearish >= 2 and bullish == 0:
        return "aligned_bearish"
    if bullish > 0 and bearish > 0:
        return "conflicting"
    return "mixed"


def technical_score(ta: Dict[str, float | str]) -> float:
    score = 50.0
    if ta.get("trend") == "uptrend":
        score += 10
    elif ta.get("trend") == "downtrend":
        score -= 10
    rsi_val = float(ta.get("rsi", 50))
    if 40 <= rsi_val <= 60:
        score += 5
    if ta.get("macd_signal") == "bullish":
        score += 8
    elif ta.get("macd_signal") == "bearish":
        score -= 8
    if float(ta.get("adx", 20)) > 25:
        score += 5
    if ta.get("ma_alignment") == "bullish":
        score += 7
    elif ta.get("ma_alignment") == "bearish":
        score -= 7
    alignment = ta.get("timeframe_alignment", "mixed")
    if alignment == "aligned_bullish":
        score += 10
    elif alignment == "aligned_bearish":
        score -= 10
    elif alignment == "conflicting":
        score -= 5
    if ta.get("breakout_state") == "breakout":
        score += 5
    elif ta.get("breakout_state") == "breakdown":
        score -= 5
    if ta.get("momentum") == "bullish":
        score += 3
    elif ta.get("momentum") == "bearish":
        score -= 3
    # Candlestick / institutional PA adjustment (bounded)
    try:
        score += float(ta.get("pattern_adj", 0.0) or 0.0)
    except (TypeError, ValueError):
        pass
    return max(0.0, min(100.0, score))


def _tf_trend(closes: Sequence[float] | None, min_bars: int = 10) -> str:
    if not closes or len(closes) < min_bars:
        return "unavailable"
    return trend_label(list(closes))


def compute_technical_analysis(
    symbol: str,
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    volumes: Sequence[float],
    benchmark_closes: Sequence[float] | None = None,
    intraday_closes: Sequence[float] | None = None,
    intraday_highs: Sequence[float] | None = None,
    intraday_lows: Sequence[float] | None = None,
    intraday_volumes: Sequence[float] | None = None,
    bars_4h: Sequence[float] | None = None,
    bars_30m: Sequence[float] | None = None,
    bars_15m: Sequence[float] | None = None,
    opens: Sequence[float] | None = None,
) -> TechnicalAnalysis:
    """Compute technicals. Daily series is primary; lower TFs optional.

    When only hourly bars are supplied, 4h is resampled from hourly and
    30m/15m are marked unavailable unless series are provided.
    """
    bench = benchmark_closes or closes
    sup, res = support_resistance(list(lows), list(highs))

    w_close, _, _, _ = resample_weekly(closes, highs, lows, volumes)
    m_close, _, _, _ = resample_bars(closes, highs, lows, volumes, 21)

    h_close = list(intraday_closes) if intraday_closes else []
    h_high = list(intraday_highs) if intraday_highs else []
    h_low = list(intraday_lows) if intraday_lows else []
    h_vol = list(intraday_volumes) if intraday_volumes else []

    if bars_4h is not None:
        c4 = list(bars_4h)
    elif h_close and h_high and h_low and h_vol:
        c4, _, _, _ = resample_bars(h_close, h_high, h_low, h_vol, 4)
    else:
        c4 = []

    c30 = list(bars_30m) if bars_30m is not None else []
    c15 = list(bars_15m) if bars_15m is not None else []

    timeframe_trends = {
        "monthly": _tf_trend(m_close, min_bars=6),
        "weekly": _tf_trend(w_close, min_bars=6),
        "daily": _tf_trend(list(closes), min_bars=10),
        "4h": _tf_trend(c4, min_bars=10),
        "1h": _tf_trend(h_close, min_bars=10),
        "30m": _tf_trend(c30, min_bars=10),
        "15m": _tf_trend(c15, min_bars=10),
    }
    # Back-compat key used by older tests/formatters
    if timeframe_trends["1h"] != "unavailable":
        timeframe_trends["intraday"] = timeframe_trends["1h"]

    alignment = timeframe_alignment(
        {k: v for k, v in timeframe_trends.items() if k != "intraday" and v != "unavailable"}
    )
    primary_trend = timeframe_trends.get("daily", "sideways")
    if primary_trend == "unavailable":
        primary_trend = "sideways"

    rsi_val = round(rsi(list(closes)), 2)
    e9 = round(ema(list(closes), 9), 4)
    e20 = round(ema(list(closes), 20), 4)
    e50 = round(ema(list(closes), 50), 4)
    e200 = round(ema(list(closes), 200), 4) if len(closes) >= 50 else e50
    brk = breakout_state(list(closes), list(highs), list(lows))
    mom = momentum_label(list(closes), rsi_val)

    pattern_report = detect_all_patterns(
        list(closes),
        list(highs),
        list(lows),
        list(volumes) if volumes else None,
        opens=list(opens) if opens else None,
    )
    candle_names = [s.name for s in pattern_report.signals if s.family == "candlestick"]
    pa_names = [
        s.name
        for s in pattern_report.signals
        if s.family in ("institutional_pa", "chart_pattern")
    ]
    pattern_notes = [s.note for s in pattern_report.signals if s.note]
    pattern_adj = pattern_score_adjustment(pattern_report)

    ta = TechnicalAnalysis(
        symbol=symbol,
        trend=primary_trend,
        rsi=rsi_val,
        macd_signal=macd_signal(list(closes)),
        adx=adx(list(highs), list(lows), list(closes)),
        atr=atr(list(highs), list(lows), list(closes)),
        bollinger_position=bollinger_position(list(closes)),
        support=sup,
        resistance=res,
        relative_strength=relative_strength(list(closes), list(bench)),
        vwap_relation=vwap_relation(
            list(intraday_closes or closes),
            list(intraday_volumes or volumes),
        ),
        ma_alignment=ma_alignment(list(closes)),
        volume_profile_bias=volume_profile_bias(list(volumes)),
        score=0.0,
        timeframe_trends=timeframe_trends,
        timeframe_alignment=alignment,
        ema_9=e9,
        ema_20=e20,
        ema_50=e50,
        ema_200=e200,
        breakout_state=brk,
        momentum=mom,
        candle_patterns=candle_names,
        pa_signals=pa_names,
        pattern_summary=pattern_report.summary(),
        pattern_notes=pattern_notes,
    )
    ta.score = technical_score(
        {
            "trend": ta.trend,
            "rsi": ta.rsi,
            "macd_signal": ta.macd_signal,
            "adx": ta.adx,
            "ma_alignment": ta.ma_alignment,
            "timeframe_alignment": alignment,
            "breakout_state": brk,
            "momentum": mom,
            "pattern_adj": pattern_adj,
        }
    )
    return ta
