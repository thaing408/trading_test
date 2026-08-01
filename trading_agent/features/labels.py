"""Horizon-aligned labels for supervised research (G2.3).

Labels use **future** bars after index ``i`` (only for training targets —
never as features). Walk-forward must not train on test labels.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass
class LabelConfig:
    horizon: int = 5
    # stop/target as fraction of price for hit-before style labels
    stop_frac: float = 0.02
    target_frac: float = 0.03
    # classification: 1 if forward return > threshold
    ret_threshold: float = 0.0


def forward_return(
    closes: Sequence[float],
    idx: int,
    horizon: int,
) -> Optional[float]:
    if idx < 0 or idx + horizon >= len(closes):
        return None
    c0 = float(closes[idx])
    c1 = float(closes[idx + horizon])
    if abs(c0) < 1e-12:
        return None
    return (c1 - c0) / c0


def hit_target_before_stop(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    idx: int,
    *,
    horizon: int,
    stop_frac: float,
    target_frac: float,
    bullish: bool = True,
) -> Optional[int]:
    """1 = target before stop, 0 = stop first or time without target, None = no path."""
    if idx + 1 >= len(closes):
        return None
    entry = float(closes[idx])
    if bullish:
        stop = entry * (1.0 - stop_frac)
        target = entry * (1.0 + target_frac)
    else:
        stop = entry * (1.0 + stop_frac)
        target = entry * (1.0 - target_frac)
    end = min(len(closes) - 1, idx + horizon)
    for j in range(idx + 1, end + 1):
        h = float(highs[j]) if j < len(highs) else float(closes[j])
        l = float(lows[j]) if j < len(lows) else float(closes[j])
        if bullish:
            if l <= stop:
                return 0
            if h >= target:
                return 1
        else:
            if h >= stop:
                return 0
            if l <= target:
                return 1
    # time exit: 1 if close above entry (bull), else 0
    last = float(closes[end])
    if bullish:
        return 1 if last > entry * (1.0 + LabelConfig.ret_threshold) else 0
    return 1 if last < entry else 0


def build_labels_for_symbol(
    pack: dict,
    indices: Sequence[int],
    *,
    config: Optional[LabelConfig] = None,
) -> Dict[int, Dict[str, float]]:
    """idx -> {fwd_ret, hit_target, y_class}."""
    cfg = config or LabelConfig()
    closes = list(pack.get("close") or [])
    highs = list(pack.get("high") or closes)
    lows = list(pack.get("low") or closes)
    out: Dict[int, Dict[str, float]] = {}
    for idx in indices:
        fr = forward_return(closes, idx, cfg.horizon)
        if fr is None:
            continue
        hit = hit_target_before_stop(
            closes,
            highs,
            lows,
            idx,
            horizon=cfg.horizon,
            stop_frac=cfg.stop_frac,
            target_frac=cfg.target_frac,
            bullish=True,
        )
        if hit is None:
            continue
        out[idx] = {
            "fwd_ret": float(fr),
            "hit_target": float(hit),
            "y_class": 1.0 if fr > cfg.ret_threshold else 0.0,
        }
    return out


def align_xy(
    X: List[List[float]],
    meta: List[dict],
    ohlcv: Dict[str, dict],
    *,
    config: Optional[LabelConfig] = None,
) -> Tuple[List[List[float]], List[float], List[dict]]:
    """Filter panel rows that have labels; y = forward return (regression)."""
    cfg = config or LabelConfig()
    label_cache: Dict[str, Dict[int, Dict[str, float]]] = {}
    Xs: List[List[float]] = []
    ys: List[float] = []
    metas: List[dict] = []
    for row, m in zip(X, meta):
        sym = m["symbol"]
        idx = int(m["idx"])
        if sym not in label_cache:
            # all indices for this symbol that appear — build once per pack
            pack = ohlcv.get(sym) or {}
            n = len(pack.get("close") or [])
            label_cache[sym] = build_labels_for_symbol(
                pack, range(25, max(26, n - cfg.horizon)), config=cfg
            )
        lab = label_cache[sym].get(idx)
        if not lab:
            continue
        Xs.append(row)
        ys.append(lab["fwd_ret"])
        metas.append({**m, "label": lab})
    return Xs, ys, metas
