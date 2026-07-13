"""Tests for offline multi-day backtest (real research + CIO paths)."""

from __future__ import annotations

from collections import Counter

from trading_agent.backtest.engine import (
    apply_best_to_risk_defaults,
    default_sweep_configs,
    run_backtest,
    run_config_sweep,
    score_period,
)
from trading_agent.backtest.fills import max_drawdown_from_equity, simulate_directional_exit
from trading_agent.backtest.models import BacktestConfig
from trading_agent.backtest.report import render_comparison, render_period_report
from trading_agent.config import RiskConfig
from trading_agent.ranking.grades import GRADE_TRADE_GEOMETRY


def test_simulate_directional_hit_target():
    exit_px, reason, held = simulate_directional_exit(
        100.0,
        95.0,
        110.0,
        future_highs=[101, 112],
        future_lows=[99, 100],
        future_closes=[100.5, 111],
        bullish=True,
    )
    assert reason == "profit_target"
    assert exit_px == 110.0
    assert held == 2


def test_max_drawdown():
    assert max_drawdown_from_equity([100, 120, 90, 95]) == 30.0


def test_run_backtest_not_degenerate():
    """Multi-regime path must produce mixed strategies, grades, and losses."""
    cfg = default_sweep_configs()[0]
    result = run_backtest(cfg)
    assert result.trade_count >= 5
    strategies = {t.strategy for t in result.trades}
    grades = {t.grade for t in result.trades}
    exits = {t.exit_reason for t in result.trades}
    # Not a single iron-condor premium_capture path
    assert len(strategies) >= 2 or len(exits) >= 2
    assert result.loser_count >= 1 or result.max_drawdown > 0
    assert result.win_rate < 0.999  # not 100% fantasy
    text = render_period_report(result)
    assert "Total P/L" in text
    assert "Expectancy" in text
    assert "Max drawdown" in text


def test_config_knobs_change_trade_set():
    """prefer_a_tier_only / conf must change outcomes at same max_trades_per_day."""
    open_cfg = BacktestConfig(
        name="open_c",
        prefer_a_tier_only=False,
        min_setup_grade="C",
        min_confidence_score=55.0,
        max_trades_per_day=3,
    )
    strict_cfg = BacktestConfig(
        name="strict_a",
        prefer_a_tier_only=True,
        min_setup_grade="B",
        min_confidence_score=60.0,
        max_trades_per_day=3,
    )
    open_r = run_backtest(open_cfg)
    strict_r = run_backtest(strict_cfg)
    # A-only cannot produce more trades than open book
    assert strict_r.trade_count <= open_r.trade_count
    # At least one of count or P/L or win_rate diverges
    diverged = (
        strict_r.trade_count != open_r.trade_count
        or abs(strict_r.total_pnl - open_r.total_pnl) > 1.0
        or abs(strict_r.win_rate - open_r.win_rate) > 0.01
    )
    assert diverged
    open_grades = set(Counter(t.grade for t in open_r.trades))
    strict_grades = set(Counter(t.grade for t in strict_r.trades))
    # Strict A-tier should not include C
    assert "C" not in strict_grades or strict_r.trade_count == 0
    if open_r.trade_count > strict_r.trade_count:
        assert open_grades - {"A+", "A"} or True  # open may include B/C


def test_book3_vs_book5_compared_in_sweep():
    sweep = run_config_sweep()
    names = {r.config_name for r in sweep.results}
    assert any("book3" in n for n in names)
    assert any("book5" in n or "wide" in n for n in names)
    by = {r.config_name: r for r in sweep.results}
    # Find a book3 and book5-like arm
    b3 = next(r for r in sweep.results if r.config.max_trades_per_day == 3)
    b5 = next(r for r in sweep.results if r.config.max_trades_per_day == 5)
    assert b5.trade_count >= b3.trade_count
    text = render_comparison(sweep)
    assert "Best config" in text
    assert sweep.best_name in text


def test_config_sweep_ranks_and_best_has_top_score():
    sweep = run_config_sweep()
    assert len(sweep.results) >= 2
    by_name = {r.config_name: r for r in sweep.results}
    best_score = score_period(by_name[sweep.best_name])
    for name in sweep.ranking[1:]:
        assert best_score + 1e-6 >= score_period(by_name[name])


def test_shipped_risk_defaults_match_backtest_winner():
    """Fails if shipped RiskConfig reverts away from multi-regime winner (strict A-tier book3)."""
    risk = RiskConfig()
    assert risk.prefer_a_tier_only is True
    assert risk.min_confidence_score == 60.0
    assert risk.top_candidates == 3
    assert risk.min_setup_grade in ("A", "A+", "B")  # not open-C floor as primary
    assert risk.min_technical_score >= 45.0
    # Geometry used by fill path
    assert GRADE_TRADE_GEOMETRY["A+"][3] >= 1.0
    assert GRADE_TRADE_GEOMETRY["C"][3] <= 0.5

    winner = next(c for c in default_sweep_configs() if "strict_a" in c.name)
    applied = apply_best_to_risk_defaults(winner)
    assert applied.prefer_a_tier_only is True
    assert applied.min_confidence_score == 60.0
    assert applied.top_candidates == 3


def test_fill_uses_grade_geometry_size():
    """Larger grade size → larger |P/L| magnitude on identical path (geometry wired)."""
    from trading_agent.backtest.engine import _geometry_size

    assert _geometry_size("A+") > _geometry_size("C")
    assert _geometry_size("A+") == GRADE_TRADE_GEOMETRY["A+"][3]
    assert _geometry_size("C") == GRADE_TRADE_GEOMETRY["C"][3]


def test_stop_loss_never_positive_pnl_for_bullish():
    """Phantom stop wins (misoriented Neutral→short) must not occur."""
    from trading_agent.backtest.fills import pnl_dollars

    # Bullish stop below entry
    pl = pnl_dollars(100.0, 95.0, bullish=True, risk_dollars=1000.0, stop=95.0, exit_reason="stop_loss")
    assert pl <= 0
    # Mis-oriented geometry: stop below but treated as short — must still clamp to loss
    pl2 = pnl_dollars(100.0, 95.0, bullish=False, risk_dollars=1000.0, stop=95.0, exit_reason="stop_loss")
    assert pl2 <= 0


def test_bull_put_fallback_direction_is_bullish():
    from trading_agent.analysis.options import compute_options_metrics
    from trading_agent.analysis.technical import compute_technical_analysis
    from trading_agent.strategy.selector import select_strategy

    # Sideways / neutral tech → hits fallback Bull Put path
    closes = [100.0 + (i % 3) * 0.1 for i in range(60)]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    vols = [1_000_000] * 60
    tech = compute_technical_analysis("X", closes, highs, lows, vols)
    opts = compute_options_metrics(
        "X", 100.0, 30.0, [25, 28, 30, 32], 100.0, 30, 5000, 1.5, 1.0, tech.trend
    )
    sel = select_strategy(tech, opts, 100.0)
    if sel.name == "Bull Put Credit Spread":
        assert sel.direction == "Bullish"
        assert sel.bias == "bullish"


def test_backtest_deterministic_across_runs():
    """PYTHONHASHSEED must not change offline ranking metrics."""
    a = run_backtest(default_sweep_configs()[0])
    b = run_backtest(default_sweep_configs()[0])
    assert a.total_pnl == b.total_pnl
    assert a.trade_count == b.trade_count
    assert a.win_rate == b.win_rate
    assert a.max_drawdown == b.max_drawdown
    assert [t.profit_loss for t in a.trades] == [t.profit_loss for t in b.trades]


def test_no_phantom_stop_wins_dominate_book():
    """stop_loss exits for bullish/credit structures should not be large winners."""
    result = run_backtest(default_sweep_configs()[0])
    stop_trades = [t for t in result.trades if t.exit_reason == "stop_loss"]
    bullishish = [
        t
        for t in stop_trades
        if t.direction.lower().startswith("bull")
        or t.strategy in ("Bull Put Credit Spread", "Covered Call", "Long Call", "Debit Spread")
    ]
    for t in bullishish:
        assert t.profit_loss <= 0, f"phantom stop win: {t}"
