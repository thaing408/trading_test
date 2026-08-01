"""Multi-sleeve competition: all methods score each ticker."""

from __future__ import annotations

from trading_agent.analysis.options import compute_options_metrics
from trading_agent.analysis.technical import compute_technical_analysis
from trading_agent.models import ScreenerCandidate
from trading_agent.strategy.competition import compete_sleeves, select_strategy_competitive


def _bars(trend_slope: float = 1.0, n: int = 60):
    closes = [100 + i * trend_slope for i in range(n)]
    highs = [c + 1.5 for c in closes]
    lows = [c - 1.5 for c in closes]
    volumes = [2_000_000] * n
    return closes, highs, lows, volumes


def _pack(trend_slope: float = 1.5, iv: float = 65.0, gap: float = 0.0, rvol: float = 2.0):
    closes, highs, lows, volumes = _bars(trend_slope)
    technical = compute_technical_analysis("TEST", closes, highs, lows, volumes)
    options = compute_options_metrics(
        symbol="TEST",
        price=closes[-1],
        iv=iv,
        iv_history=[iv - 5, iv - 2, iv, iv - 1, iv + 1],
        strike=closes[-1] * 1.02,
        days_to_expiry=30,
        open_interest=5000,
        relative_volume=rvol,
        bid_ask_spread_pct=1.0,
        trend=technical.trend,
    )
    candidate = ScreenerCandidate(
        symbol="TEST",
        price=closes[-1],
        volume=int(volumes[-1]),
        relative_volume=rvol,
        options_liquidity_score=70.0,
        open_interest=5000,
        bid_ask_spread_pct=1.0,
        sector="Technology",
        avg_daily_volume=3_000_000,
        institutional_score=75.0,
        gap_pct=gap,
    )
    return candidate, technical, options


def test_compete_returns_scoreboard():
    cand, tech, opt = _pack()
    result = compete_sleeves(cand, tech, opt)
    assert result.symbol == "TEST"
    assert len(result.scoreboard) >= 4
    ids = {s.sleeve_id for s in result.scoreboard}
    assert "momentum_rs" in ids
    assert "gap_continuation" in ids
    assert "orb_vwap" in ids
    assert "mean_reversion" in ids


def test_high_iv_has_winner():
    cand, tech, opt = _pack(trend_slope=2.0, iv=75.0)
    result = compete_sleeves(cand, tech, opt)
    assert result.winner is not None
    assert result.winner.strategy is not None
    assert result.scoreboard[0].score >= result.scoreboard[-1].score


def test_gap_sleeve_viable_on_gap():
    cand, tech, opt = _pack(trend_slope=1.0, iv=40.0, gap=3.5, rvol=2.5)
    result = compete_sleeves(cand, tech, opt)
    gap = next(s for s in result.scoreboard if s.sleeve_id == "gap_continuation")
    assert gap.viable
    assert gap.score >= 50


def test_select_strategy_competitive_tuple():
    cand, tech, opt = _pack(iv=70)
    st, setup_id, comp = select_strategy_competitive(cand, tech, opt)
    assert st.name
    assert setup_id
    assert len(comp.scoreboard) > 0


def test_scoreboard_summary_format():
    cand, tech, opt = _pack()
    result = compete_sleeves(cand, tech, opt)
    text = result.scoreboard_summary(3)
    assert "WIN" in text or "—" in text
