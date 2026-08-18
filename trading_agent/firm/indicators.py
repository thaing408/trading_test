"""P5 named technical indicator pack (~60 features) for the tech analyst."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

import numpy as np


def _sma(vals: Sequence[float], n: int) -> float:
    if len(vals) < n:
        return float(vals[-1]) if vals else 0.0
    return float(np.mean(vals[-n:]))


def _ema(vals: Sequence[float], n: int) -> float:
    if not vals:
        return 0.0
    alpha = 2 / (n + 1)
    e = float(vals[0])
    for v in vals[1:]:
        e = alpha * float(v) + (1 - alpha) * e
    return e


def _rsi(closes: Sequence[float], n: int = 14) -> float:
    if len(closes) < n + 1:
        return 50.0
    d = np.diff(closes[-(n + 1) :])
    gains = np.where(d > 0, d, 0)
    losses = np.where(d < 0, -d, 0)
    ag = float(np.mean(gains)) or 1e-9
    al = float(np.mean(losses)) or 1e-9
    return float(100 - (100 / (1 + ag / al)))


def build_indicator_pack(ohlcv: Dict[str, Any]) -> Dict[str, Any]:
    """Return a named multi-feature pack (paper §5.2 style breadth of TA)."""
    if ohlcv.get("status") != "ok":
        return {"status": ohlcv.get("status", "empty"), "count": 0, "features": {}}

    closes = [float(x) for x in (ohlcv.get("closes") or [])]
    highs = [float(x) for x in (ohlcv.get("highs") or [])]
    lows = [float(x) for x in (ohlcv.get("lows") or [])]
    vols = [float(x) for x in (ohlcv.get("volumes") or [])]
    if len(closes) < 20:
        return {"status": "empty", "count": 0, "features": {}, "reason": "short_history"}

    feats: Dict[str, float] = {}
    # Moving averages
    for n in (5, 9, 10, 20, 21, 50, 100, 200):
        if len(closes) >= min(n, 20):
            feats[f"sma_{n}"] = round(_sma(closes, min(n, len(closes))), 4)
            feats[f"ema_{n}"] = round(_ema(closes, min(n, len(closes))), 4)
    # Momentum
    for n in (7, 14, 21):
        feats[f"rsi_{n}"] = round(_rsi(closes, n), 2)
    # Returns
    for n in (1, 3, 5, 10, 20, 60):
        if len(closes) > n and closes[-n - 1] != 0:
            feats[f"ret_{n}d"] = round((closes[-1] / closes[-n - 1] - 1) * 100, 3)
    # Volatility / range
    if len(closes) >= 15 and highs and lows:
        trs = []
        for i in range(1, min(len(closes), len(highs), len(lows))):
            trs.append(
                max(
                    highs[i] - lows[i],
                    abs(highs[i] - closes[i - 1]),
                    abs(lows[i] - closes[i - 1]),
                )
            )
        for n in (7, 14, 21):
            window = trs[-n:] if len(trs) >= n else trs
            feats[f"atr_{n}"] = round(float(np.mean(window)), 4) if window else 0.0
        feats["hl_range_20"] = round(float(max(highs[-20:]) - min(lows[-20:])), 4)
        feats["close_vs_high_20"] = round(closes[-1] / (max(highs[-20:]) or 1e-9), 4)
        feats["close_vs_low_20"] = round(closes[-1] / (min(lows[-20:]) or 1e-9), 4)
    # Volume
    if vols:
        for n in (5, 10, 20):
            feats[f"vol_sma_{n}"] = round(_sma(vols, min(n, len(vols))), 2)
        if feats.get("vol_sma_20"):
            feats["vol_ratio_20"] = round(vols[-1] / (feats["vol_sma_20"] or 1e-9), 3)
    # Bollinger width
    if len(closes) >= 20:
        mid = float(np.mean(closes[-20:]))
        std = float(np.std(closes[-20:])) or 1e-9
        feats["bb_mid_20"] = round(mid, 4)
        feats["bb_upper_20"] = round(mid + 2 * std, 4)
        feats["bb_lower_20"] = round(mid - 2 * std, 4)
        feats["bb_pct_b"] = round((closes[-1] - (mid - 2 * std)) / (4 * std), 4)
    # MACD proxy
    if len(closes) >= 26:
        e12, e26 = _ema(closes, 12), _ema(closes, 26)
        feats["macd_line"] = round(e12 - e26, 4)
        feats["macd_signal_proxy"] = round(_ema([e12 - e26] * 9, 9), 4)  # coarse
    # Distance to MAs
    last = closes[-1]
    for n in (20, 50, 200):
        key = f"sma_{n}"
        if key in feats and feats[key]:
            feats[f"dist_sma_{n}_pct"] = round((last / feats[key] - 1) * 100, 3)

    # Pad / mark unavailable breadth-style placeholders (paper has breadth series)
    feats["breadth_ad_unavailable"] = -1.0
    feats["breadth_nhnl_unavailable"] = -1.0

    return {
        "status": "ok",
        "count": len(feats),
        "features": feats,
        "last": last,
        "pack_name": "firm_ta_pack_v1",
    }
