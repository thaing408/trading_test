"""Production-path rails: build_opportunities + pipeline wire RiskConfig + stop-out book."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trading_agent.config import RiskConfig
from trading_agent.discipline.rails import (
    build_session_risk_state,
    load_stopout_book,
    record_stopout_event,
    session_state_from_risk_config,
)
from trading_agent.models import OptionsMetrics, RejectedSetup, ScreenerCandidate, TechnicalAnalysis
from trading_agent.ranking.ranker import build_opportunities


def _tech(symbol="NVDA", **kw):
    base = dict(
        symbol=symbol,
        trend="uptrend",
        rsi=52.0,
        macd_signal="bullish",
        adx=28.0,
        atr=3.0,
        bollinger_position="mid",
        support=100.0,
        resistance=130.0,
        relative_strength=1.2,
        vwap_relation="above",
        ma_alignment="bullish",
        volume_profile_bias="accumulation",
        score=78.0,
        timeframe_trends={"daily": "uptrend", "weekly": "uptrend", "1h": "uptrend"},
        timeframe_alignment="aligned_bullish",
        breakout_state="breakout",
        momentum="bullish",
        ema_9=112.0,
        ema_20=110.0,
        ema_50=105.0,
        ema_200=95.0,
    )
    base.update(kw)
    return TechnicalAnalysis(**base)


def _opts(symbol="NVDA"):
    return OptionsMetrics(
        symbol=symbol,
        implied_volatility=28.0,
        iv_rank=35.0,
        iv_percentile=40.0,
        expected_move_pct=2.0,
        delta=0.55,
        gamma=0.04,
        theta=-0.04,
        vega=0.12,
        unusual_activity=True,
        institutional_flow_bias="bullish",
        liquidity_score=75.0,
        probability_of_profit=0.58,
        probability_of_touch=0.4,
        options_volume=20000,
        open_interest=8000,
        bid_ask_spread_pct=1.2,
    )


def _cand(symbol="NVDA", **kw):
    base = dict(
        symbol=symbol,
        price=115.0,
        volume=8_000_000,
        avg_daily_volume=5_000_000,
        relative_volume=2.8,
        market_cap=2e12,
        sector="Technology",
        open_interest=8000,
        bid_ask_spread_pct=1.0,
        institutional_score=75.0,
        options_volume=20000,
        options_liquidity_score=75.0,
        gap_pct=1.0,
    )
    base.update(kw)
    return ScreenerCandidate(**base)


def _risk(**kw) -> RiskConfig:
    cfg = RiskConfig(
        min_confidence_score=50.0,
        prefer_a_tier_only=False,
        min_setup_grade="C",
        top_candidates=5,
        require_playbook_checklist=True,
        require_edge_package=True,
        enforce_mtf_gate=True,
        enforce_discipline_rails=True,
        enforce_fundamental_gate=False,
        min_combined_quality_score=0.0,
        max_concurrent_plays=3,
        max_aggregate_risk_pct=6.0,
        max_risk_per_trade_pct=2.0,
        stop_cooldown_minutes=60,
    )
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


def test_session_state_reads_risk_config_limits():
    risk = _risk(max_concurrent_plays=2, max_aggregate_risk_pct=4.0, stop_cooldown_minutes=90)
    state = session_state_from_risk_config(risk)
    assert state.max_concurrent_plays == 2
    assert state.max_new_risk_pct == 4.0
    assert state.cooldown_minutes == 90
    assert state.max_risk_per_trade_pct == 2.0


def test_build_opportunities_always_applies_rails_without_explicit_state():
    """Ranker seeds SessionRiskState from RiskConfig even when session_state is None."""
    risk = _risk(max_concurrent_plays=0)  # zero concurrent → block all new symbols
    # max_concurrent 0 means open_count >= 0 for any new symbol
    rail_rej: list = []
    opps = build_opportunities(
        [(_cand("AAA"), _tech("AAA"), _opts("AAA"))],
        risk,
        session_state=None,
        rail_rejections=rail_rej,
    )
    assert opps == []
    assert rail_rej
    assert any("concurrent" in r.reason.lower() for r in rail_rej)


def test_stopout_book_blocks_revenge_on_build_opportunities(tmp_path: Path):
    stop_path = tmp_path / "stopouts.json"
    now = datetime.now(timezone.utc)
    stop_path.write_text(
        json.dumps(
            {
                "stop_outs": [
                    {
                        "symbol": "TSLA",
                        "time": (now - timedelta(minutes=5)).isoformat(),
                        "reason": "stop_loss",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    risk = _risk()
    state = build_session_risk_state(
        risk,
        stopout_path=stop_path,
        open_symbols=[],
        open_risk_pct=0.0,
    )
    assert any(s["symbol"] == "TSLA" for s in state.stop_outs)

    rail_rej: list[RejectedSetup] = []
    opps = build_opportunities(
        [(_cand("TSLA"), _tech("TSLA"), _opts("TSLA"))],
        risk,
        session_state=state,
        rail_rejections=rail_rej,
    )
    assert opps == []
    assert any("cool-down" in r.reason.lower() or "revenge" in r.reason.lower() for r in rail_rej)


def test_open_book_blocks_when_max_concurrent_reached(tmp_path: Path):
    risk = _risk(max_concurrent_plays=2, max_aggregate_risk_pct=10.0)
    state = build_session_risk_state(
        risk,
        open_symbols=["AAPL", "MSFT"],
        open_risk_pct=4.0,
        stop_outs=[],
    )
    assert state.max_concurrent_plays == 2
    rail_rej: list = []
    opps = build_opportunities(
        [(_cand("NVDA"), _tech("NVDA"), _opts("NVDA"))],
        risk,
        session_state=state,
        rail_rejections=rail_rej,
    )
    assert opps == []
    assert any("concurrent" in r.reason.lower() for r in rail_rej)


def test_record_stopout_event_persists_and_loads(tmp_path: Path):
    path = tmp_path / "book.json"
    record_stopout_event("QQQ", when=datetime.now(timezone.utc), path=path)
    rows = load_stopout_book(path)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "QQQ"


def test_pipeline_source_wires_build_session_risk_state():
    """Structural + behavioral: pipeline.py must call build_session_risk_state and pass session_state."""
    src = Path(__file__).resolve().parents[1] / "trading_agent" / "pipeline.py"
    text = src.read_text(encoding="utf-8")
    assert "build_session_risk_state" in text
    assert "session_state=session_state" in text
    assert "rail_rejections" in text


def test_ranker_reads_max_concurrent_from_risk_config_into_state():
    risk = _risk(max_concurrent_plays=1, max_aggregate_risk_pct=2.5, stop_cooldown_minutes=45)
    state = session_state_from_risk_config(risk)
    # Mutate then apply_risk_config again as ranker does
    state.max_concurrent_plays = 99
    state.apply_risk_config(risk)
    assert state.max_concurrent_plays == 1
    assert state.max_new_risk_pct == 2.5
    assert state.cooldown_minutes == 45


def test_intra_batch_max_concurrent_record_open_limits_opportunities():
    """Empty open book + max_concurrent_plays=1 + ≥2 eligible → only 1 opportunity.

    Proves build_opportunities calls record_open after each accept so one rank
    pass cannot emit N > max_concurrent_plays (criterion 5 / skeptic gap).
    """
    risk = _risk(
        max_concurrent_plays=1,
        max_aggregate_risk_pct=10.0,
        top_candidates=5,
        max_risk_per_trade_pct=2.0,
    )
    # Explicit empty book — only intra-batch claiming should fill concurrent
    state = build_session_risk_state(
        risk,
        open_symbols=[],
        open_risk_pct=0.0,
        stop_outs=[],
    )
    assert state.open_symbols == []
    assert state.max_concurrent_plays == 1

    qualified = [
        (_cand("AAA"), _tech("AAA"), _opts("AAA")),
        (_cand("BBB"), _tech("BBB"), _opts("BBB")),
        (_cand("CCC"), _tech("CCC"), _opts("CCC")),
    ]
    rail_rej: list[RejectedSetup] = []
    opps = build_opportunities(
        qualified,
        risk,
        session_state=state,
        rail_rejections=rail_rej,
    )
    assert len(opps) == 1, f"expected 1 opp under max_concurrent=1, got {len(opps)}: {[o.symbol for o in opps]}"
    assert opps[0].rank == 1
    # Session book must show the accepted symbol claimed
    assert opps[0].symbol.upper() in {s.upper() for s in state.open_symbols}
    # At least one other eligible name rejected for concurrent
    concurrent_rejs = [
        r
        for r in rail_rej
        if "concurrent" in r.reason.lower() and r.symbol.upper() != opps[0].symbol.upper()
    ]
    assert concurrent_rejs, f"expected concurrent rejections, got: {[r.reason for r in rail_rej]}"


def test_intra_batch_aggregate_risk_blocks_second():
    """Empty book, max_aggregate_risk_pct equals one trade → second name blocked."""
    risk = _risk(
        max_concurrent_plays=5,
        max_aggregate_risk_pct=2.0,  # exactly one max_risk_per_trade_pct=2.0 slot
        max_risk_per_trade_pct=2.0,
        top_candidates=5,
    )
    state = build_session_risk_state(
        risk, open_symbols=[], open_risk_pct=0.0, stop_outs=[]
    )
    rail_rej: list = []
    opps = build_opportunities(
        [
            (_cand("X1"), _tech("X1"), _opts("X1")),
            (_cand("X2"), _tech("X2"), _opts("X2")),
        ],
        risk,
        session_state=state,
        rail_rejections=rail_rej,
    )
    assert len(opps) == 1
    assert any("aggregate" in r.reason.lower() for r in rail_rej)
