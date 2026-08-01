"""Linear ranker (ridge) with baseline gate (G2.4 / G2.5).

Classical baseline = score by ret_5 / mom_20 heuristic (no fit).
ML model = ridge regression on feature schema v1 predicting forward return.

**Promotion rule:** ML only "beats baseline" when OOS IC or directional accuracy
improves on hold-out folds — never auto-ships into live gates.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from trading_agent.features.builder import FEATURE_NAMES, build_panel
from trading_agent.features.labels import LabelConfig, align_xy


@dataclass
class LinearRanker:
    """Ridge regression y ~ Xw (forward returns)."""

    weights: List[float] = field(default_factory=list)
    bias: float = 0.0
    feature_names: Tuple[str, ...] = FEATURE_NAMES
    ridge: float = 1.0
    schema_version: str = "1.0.0"

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float]) -> "LinearRanker":
        arr = np.asarray(X, dtype=float)
        yy = np.asarray(y, dtype=float)
        if arr.ndim != 2 or arr.shape[0] < 5 or arr.shape[0] != yy.shape[0]:
            self.weights = [0.0] * (arr.shape[1] if arr.ndim == 2 else len(FEATURE_NAMES))
            self.bias = float(np.mean(yy)) if yy.size else 0.0
            return self
        # standardize
        mu = arr.mean(axis=0)
        sigma = arr.std(axis=0)
        sigma = np.where(sigma < 1e-8, 1.0, sigma)
        Z = (arr - mu) / sigma
        # design with bias
        ones = np.ones((Z.shape[0], 1))
        A = np.hstack([ones, Z])
        n_f = A.shape[1]
        reg = self.ridge * np.eye(n_f)
        reg[0, 0] = 0.0
        try:
            coef = np.linalg.solve(A.T @ A + reg, A.T @ yy)
        except np.linalg.LinAlgError:
            coef = np.linalg.lstsq(A.T @ A + reg, A.T @ yy, rcond=None)[0]
        self.bias = float(coef[0])
        # store weights in original feature space: w_raw = w_z / sigma
        w_z = coef[1:]
        self.weights = list((w_z / sigma).astype(float))
        self._mu = list(mu.astype(float))  # type: ignore[attr-defined]
        self._sigma = list(sigma.astype(float))  # type: ignore[attr-defined]
        # Actually predict uses unstandardized if we transform weights wrong.
        # Simpler: store mu/sigma and z-score at predict.
        self._use_z = True  # type: ignore[attr-defined]
        self.weights = list(w_z.astype(float))
        return self

    def predict(self, X: Sequence[Sequence[float]]) -> List[float]:
        arr = np.asarray(X, dtype=float)
        if arr.size == 0:
            return []
        if not self.weights:
            return [0.0] * arr.shape[0]
        w = np.asarray(self.weights, dtype=float)
        if getattr(self, "_use_z", False) and hasattr(self, "_mu"):
            mu = np.asarray(self._mu, dtype=float)
            sigma = np.asarray(self._sigma, dtype=float)
            Z = (arr - mu) / sigma
            pred = self.bias + Z @ w
        else:
            pred = self.bias + arr @ w
        return [float(p) for p in pred]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "weights": self.weights,
            "bias": self.bias,
            "ridge": self.ridge,
            "schema_version": self.schema_version,
            "feature_names": list(self.feature_names),
            "mu": getattr(self, "_mu", None),
            "sigma": getattr(self, "_sigma", None),
        }


def baseline_scores(X: Sequence[Sequence[float]], feature_names: Sequence[str] = FEATURE_NAMES) -> List[float]:
    """Unfitted baseline: 0.5*ret_5 + 0.5*mom_20 (classical momentum)."""
    names = list(feature_names)
    try:
        i5 = names.index("ret_5")
        i20 = names.index("mom_20")
    except ValueError:
        return [0.0] * len(X)
    out = []
    for row in X:
        r5 = float(row[i5]) if i5 < len(row) else 0.0
        r20 = float(row[i20]) if i20 < len(row) else 0.0
        out.append(0.5 * r5 + 0.5 * r20)
    return out


def information_coefficient(pred: Sequence[float], y: Sequence[float]) -> float:
    """Spearman-ish via Pearson on ranks; Pearson on raw if short."""
    if len(pred) < 3 or len(pred) != len(y):
        return 0.0
    p = np.asarray(pred, dtype=float)
    t = np.asarray(y, dtype=float)
    if np.std(p) < 1e-12 or np.std(t) < 1e-12:
        return 0.0
    # pearson
    p0 = p - p.mean()
    t0 = t - t.mean()
    return float(np.dot(p0, t0) / (np.linalg.norm(p0) * np.linalg.norm(t0) + 1e-12))


def directional_accuracy(pred: Sequence[float], y: Sequence[float]) -> float:
    if not pred or len(pred) != len(y):
        return 0.0
    correct = sum(1 for a, b in zip(pred, y) if (a >= 0 and b >= 0) or (a < 0 and b < 0))
    return correct / len(pred)


@dataclass
class RankerComparison:
    baseline_ic: float
    ml_ic: float
    baseline_dir_acc: float
    ml_dir_acc: float
    n: int
    ml_beats_baseline: bool
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compare_rankers(
    baseline_pred: Sequence[float],
    ml_pred: Sequence[float],
    y: Sequence[float],
    *,
    min_ic_edge: float = 0.02,
) -> RankerComparison:
    b_ic = information_coefficient(baseline_pred, y)
    m_ic = information_coefficient(ml_pred, y)
    b_da = directional_accuracy(baseline_pred, y)
    m_da = directional_accuracy(ml_pred, y)
    beats = (m_ic >= b_ic + min_ic_edge) or (m_ic > b_ic and m_da > b_da)
    reason = (
        f"ml_ic={m_ic:.3f} vs base_ic={b_ic:.3f}; "
        f"ml_dir={m_da:.3f} vs base_dir={b_da:.3f}"
    )
    if not beats:
        reason += " — ML does NOT beat baseline (do not promote)"
    else:
        reason += " — ML beats baseline on this fold (paper only)"
    return RankerComparison(
        baseline_ic=round(b_ic, 4),
        ml_ic=round(m_ic, 4),
        baseline_dir_acc=round(b_da, 4),
        ml_dir_acc=round(m_da, 4),
        n=len(y),
        ml_beats_baseline=beats,
        reason=reason,
    )


def train_ranker_walk_forward(
    ohlcv: Dict[str, dict],
    *,
    train_bars: int = 80,
    test_bars: int = 20,
    step_bars: int = 20,
    embargo: int = 5,
    label_cfg: Optional[LabelConfig] = None,
    ridge: float = 1.0,
) -> Dict[str, Any]:
    """Fit linear ranker each fold; report OOS vs baseline."""
    from trading_agent.backtest.walk_forward import make_walk_forward_windows

    cfg = label_cfg or LabelConfig(horizon=5)
    syms = list(ohlcv.keys())
    n = min(len(ohlcv[s]["close"]) for s in syms) if syms else 0
    windows = make_walk_forward_windows(
        n,
        train_bars=train_bars,
        test_bars=test_bars,
        step_bars=step_bars,
        embargo_bars=embargo,
        min_start=25,
    )
    fold_rows: List[Dict[str, Any]] = []
    beats = 0
    for win in windows:
        train_idx = list(range(win.train_start, win.train_end))
        test_idx = list(range(win.test_start, win.test_end - cfg.horizon))
        if len(test_idx) < 3 or len(train_idx) < 10:
            continue
        Xtr, mtr, _ = build_panel(ohlcv, indices=train_idx, symbols=syms)
        Xtr, ytr, _ = align_xy(Xtr, mtr, ohlcv, config=cfg)
        Xte, mte, _ = build_panel(ohlcv, indices=test_idx, symbols=syms)
        Xte, yte, _ = align_xy(Xte, mte, ohlcv, config=cfg)
        if len(ytr) < 10 or len(yte) < 3:
            continue
        model = LinearRanker(ridge=ridge).fit(Xtr, ytr)
        ml_pred = model.predict(Xte)
        base_pred = baseline_scores(Xte)
        comp = compare_rankers(base_pred, ml_pred, yte)
        if comp.ml_beats_baseline:
            beats += 1
        fold_rows.append({"fold": win.fold, **comp.to_dict()})

    n_folds = len(fold_rows)
    summary = {
        "folds": n_folds,
        "folds_ml_beats_baseline": beats,
        "promote_ml": bool(n_folds >= 2 and beats > n_folds / 2),
        "message": (
            "ML wins majority of OOS folds — eligible for paper ranking experiment"
            if (n_folds >= 2 and beats > n_folds / 2)
            else "Keep classical baseline; ML not promoted"
        ),
        "fold_results": fold_rows,
        "schema_version": "1.0.0",
        "label_horizon": cfg.horizon,
    }
    return summary


def format_ranker_report(summary: Dict[str, Any]) -> str:
    lines = [
        "# Feature ranker walk-forward (vs classical baseline)",
        f"Schema: {summary.get('schema_version')}  horizon={summary.get('label_horizon')}",
        f"Folds: {summary.get('folds')}  ML beats: {summary.get('folds_ml_beats_baseline')}",
        f"**Promote ML (paper only):** {summary.get('promote_ml')}",
        f"_{summary.get('message')}_",
        "",
        "## Folds",
    ]
    for row in summary.get("fold_results") or []:
        lines.append(
            f"- fold {row.get('fold')}: base_IC={row.get('baseline_ic')} "
            f"ml_IC={row.get('ml_ic')} base_dir={row.get('baseline_dir_acc')} "
            f"ml_dir={row.get('ml_dir_acc')} n={row.get('n')} "
            f"beats={row.get('ml_beats_baseline')}"
        )
    if not summary.get("fold_results"):
        lines.append("- _No folds (need longer history)._")
    return "\n".join(lines) + "\n"
