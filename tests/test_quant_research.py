"""Historical helpers (synthetic), walk-forward, features, ML ranker gate."""

from __future__ import annotations

from trading_agent.backtest.data import default_backtest_universe
from trading_agent.backtest.engine import default_sweep_configs
from trading_agent.backtest.historical import align_ohlcv
from trading_agent.backtest.walk_forward import make_walk_forward_windows, run_walk_forward
from trading_agent.features.builder import FEATURE_SCHEMA_VERSION, build_feature_row, build_panel
from trading_agent.features.labels import LabelConfig, align_xy, forward_return
from trading_agent.ml.ranker import (
    LinearRanker,
    baseline_scores,
    compare_rankers,
    train_ranker_walk_forward,
)
from trading_agent.research.quant_pipeline import run_quant_research


def test_align_ohlcv_trims_to_min():
    data = {
        "A": {"close": list(range(100)), "high": list(range(100)), "low": list(range(100)), "volume": [1] * 100},
        "B": {"close": list(range(80)), "high": list(range(80)), "low": list(range(80)), "volume": [1] * 80},
    }
    out = align_ohlcv(data)
    assert len(out["A"]["close"]) == 80
    assert len(out["B"]["close"]) == 80


def test_walk_forward_windows():
    wins = make_walk_forward_windows(200, train_bars=60, test_bars=20, step_bars=20, embargo_bars=5, min_start=30)
    assert len(wins) >= 2
    for w in wins:
        assert w.train_end <= w.test_start - w.embargo
        assert w.test_end <= 200


def test_walk_forward_on_synthetic():
    ohlcv = default_backtest_universe()
    for s in ohlcv:
        ohlcv[s]["source"] = "synthetic"
    cfg = default_sweep_configs()[0]
    # shorter windows for 100-bar multi-regime (~100 bars)
    report = run_walk_forward(
        cfg,
        ohlcv,
        train_bars=40,
        test_bars=15,
        step_bars=15,
        embargo_bars=3,
    )
    assert report.n_bars > 50
    assert report.aggregate["folds"] >= 1
    # at least runs without crash
    assert "oos_total_trades" in report.aggregate


def test_feature_row_no_lookahead_length():
    closes = [100.0 + i * 0.1 for i in range(50)]
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    vols = [1e6] * 50
    assert build_feature_row(closes, highs, lows, vols, 10) is None
    row = build_feature_row(closes, highs, lows, vols, 30)
    assert row is not None
    assert "ret_5" in row
    assert row["rsi_14"] >= 0


def test_panel_and_labels():
    ohlcv = default_backtest_universe()
    X, meta, names = build_panel(ohlcv)
    assert names
    assert FEATURE_SCHEMA_VERSION
    assert len(X) == len(meta)
    X2, y, m2 = align_xy(X, meta, ohlcv, config=LabelConfig(horizon=5))
    assert len(X2) == len(y) == len(m2)
    assert len(y) > 50


def test_linear_ranker_fit_predict():
    X = [[float(i), float(i * 2)] for i in range(20)]
    y = [0.01 * i for i in range(20)]
    model = LinearRanker(ridge=0.5)
    # pad to feature dim
    from trading_agent.features.builder import FEATURE_NAMES

    Xf = []
    for row in X:
        full = [0.0] * len(FEATURE_NAMES)
        full[0] = row[0]
        full[1] = row[1]
        Xf.append(full)
    model.fit(Xf, y)
    pred = model.predict(Xf[:3])
    assert len(pred) == 3


def test_compare_rankers_structure():
    y = [0.1, -0.1, 0.05, -0.02, 0.03]
    base = [0.1, -0.05, 0.01, 0.0, 0.02]
    ml = [0.12, -0.11, 0.04, -0.03, 0.05]
    comp = compare_rankers(base, ml, y, min_ic_edge=0.0)
    assert comp.n == 5
    assert "ml_ic" in comp.to_dict()


def test_train_ranker_walk_forward_synthetic():
    ohlcv = default_backtest_universe()
    summary = train_ranker_walk_forward(
        ohlcv,
        train_bars=40,
        test_bars=15,
        step_bars=15,
        embargo=3,
    )
    assert "promote_ml" in summary
    assert summary["folds"] >= 1


def test_quant_pipeline_synthetic():
    pack = run_quant_research(
        historical=False,
        train_bars=40,
        test_bars=15,
        step_bars=15,
        embargo_bars=3,
        include_ml=True,
    )
    assert pack["n_symbols"] >= 5
    assert pack["walk_forward"]["aggregate"]["folds"] >= 1
    assert pack["ml"] is not None


def test_forward_return():
    closes = [100.0, 101.0, 102.0, 103.0, 104.0]
    assert abs(forward_return(closes, 0, 2) - 0.02) < 1e-9
    assert forward_return(closes, 3, 2) is None


def test_baseline_scores_len():
    from trading_agent.features.builder import FEATURE_NAMES

    X = [[0.0] * len(FEATURE_NAMES) for _ in range(4)]
    X[0][FEATURE_NAMES.index("ret_5")] = 0.02
    scores = baseline_scores(X)
    assert len(scores) == 4
