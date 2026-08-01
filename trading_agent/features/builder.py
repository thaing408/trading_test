"""Point-in-time feature vectors from OHLCV (no look-ahead).

All features at index ``i`` use only bars ``<= i``.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

FEATURE_SCHEMA_VERSION = "1.0.0"

# Stable column order for ML
FEATURE_NAMES: Tuple[str, ...] = (
    "ret_1",
    "ret_5",
    "ret_10",
    "ret_20",
    "vol_10",
    "vol_20",
    "range_pct",
    "close_loc",  # (c-l)/(h-l)
    "rvol_20",
    "mom_20",
    "rsi_14",
    "ma_ratio_10",
    "ma_ratio_20",
    "high_20_dist",
    "low_20_dist",
    "cs_ret_5_rank",  # cross-sectional rank 0-1 (filled in panel)
    "cs_mom_20_rank",
)


def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    if b == 0 or b is None or (isinstance(b, float) and abs(b) < 1e-12):
        return default
    return a / b


def _rsi(closes: Sequence[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains = 0.0
    losses = 0.0
    for i in range(-period, 0):
        d = closes[i] - closes[i - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    if losses < 1e-12:
        return 100.0
    rs = gains / losses
    return 100.0 - (100.0 / (1.0 + rs))


def build_feature_row(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    volumes: Sequence[float],
    idx: int,
) -> Optional[Dict[str, float]]:
    """Features at bar ``idx`` using only history through idx. None if insufficient."""
    if idx < 25 or idx >= len(closes):
        return None
    c = float(closes[idx])
    h = float(highs[idx]) if idx < len(highs) else c
    l = float(lows[idx]) if idx < len(lows) else c
    v = float(volumes[idx]) if idx < len(volumes) else 0.0

    def ret(n: int) -> float:
        if idx < n:
            return 0.0
        prev = float(closes[idx - n])
        return _safe_div(c - prev, prev)

    # realized vol of 1d returns
    def vol(n: int) -> float:
        if idx < n + 1:
            return 0.0
        rets = []
        for j in range(idx - n + 1, idx + 1):
            p0 = float(closes[j - 1])
            p1 = float(closes[j])
            rets.append(_safe_div(p1 - p0, p0))
        if not rets:
            return 0.0
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / max(1, len(rets) - 1)
        return math.sqrt(max(0.0, var))

    window_v = [float(volumes[j]) for j in range(max(0, idx - 19), idx + 1)]
    avg_v = sum(window_v) / max(1, len(window_v))

    hi20 = max(float(highs[j]) for j in range(idx - 19, idx + 1))
    lo20 = min(float(lows[j]) for j in range(idx - 19, idx + 1))
    ma10 = sum(float(closes[j]) for j in range(idx - 9, idx + 1)) / 10.0
    ma20 = sum(float(closes[j]) for j in range(idx - 19, idx + 1)) / 20.0

    row = {
        "ret_1": ret(1),
        "ret_5": ret(5),
        "ret_10": ret(10),
        "ret_20": ret(20),
        "vol_10": vol(10),
        "vol_20": vol(20),
        "range_pct": _safe_div(h - l, c),
        "close_loc": _safe_div(c - l, h - l, 0.5),
        "rvol_20": _safe_div(v, avg_v, 1.0),
        "mom_20": ret(20),
        "rsi_14": _rsi(list(closes[: idx + 1]), 14) / 100.0,
        "ma_ratio_10": _safe_div(c, ma10, 1.0) - 1.0,
        "ma_ratio_20": _safe_div(c, ma20, 1.0) - 1.0,
        "high_20_dist": _safe_div(c - hi20, c),
        "low_20_dist": _safe_div(c - lo20, c),
        "cs_ret_5_rank": 0.5,  # filled in panel
        "cs_mom_20_rank": 0.5,
    }
    return row


def vectorize(row: Dict[str, float]) -> List[float]:
    return [float(row.get(name, 0.0)) for name in FEATURE_NAMES]


def build_panel(
    ohlcv: Dict[str, dict],
    *,
    indices: Optional[Sequence[int]] = None,
    symbols: Optional[Sequence[str]] = None,
) -> Tuple[List[List[float]], List[Dict[str, Any]], List[str]]:
    """Build feature matrix X, metadata rows, feature names.

    Cross-sectional ranks computed per date index across symbols.
    """
    syms = list(symbols) if symbols else list(ohlcv.keys())
    if not syms:
        return [], [], list(FEATURE_NAMES)

    n = min(len(ohlcv[s]["close"]) for s in syms if s in ohlcv)
    if indices is None:
        indices = list(range(25, n))

    # First pass: raw features per (sym, idx)
    raw: Dict[Tuple[str, int], Dict[str, float]] = {}
    for idx in indices:
        if idx >= n:
            continue
        day_rows: Dict[str, Dict[str, float]] = {}
        for sym in syms:
            pack = ohlcv.get(sym)
            if not pack:
                continue
            closes = pack.get("close") or []
            if idx >= len(closes):
                continue
            row = build_feature_row(
                closes,
                pack.get("high") or closes,
                pack.get("low") or closes,
                pack.get("volume") or [1e6] * len(closes),
                idx,
            )
            if row:
                day_rows[sym] = row
        # cross-sectional ranks
        if day_rows:
            for key, feat in (("ret_5", "cs_ret_5_rank"), ("mom_20", "cs_mom_20_rank")):
                ordered = sorted(day_rows.keys(), key=lambda s: day_rows[s].get(key, 0.0))
                m = max(1, len(ordered) - 1)
                for rank, s in enumerate(ordered):
                    day_rows[s][feat] = rank / m
        for sym, row in day_rows.items():
            raw[(sym, idx)] = row

    X: List[List[float]] = []
    meta: List[Dict[str, Any]] = []
    for (sym, idx), row in sorted(raw.items(), key=lambda x: (x[0][1], x[0][0])):
        X.append(vectorize(row))
        meta.append(
            {
                "symbol": sym,
                "idx": idx,
                "schema": FEATURE_SCHEMA_VERSION,
                "close": float(ohlcv[sym]["close"][idx]),
                "features": row,
            }
        )
    return X, meta, list(FEATURE_NAMES)
