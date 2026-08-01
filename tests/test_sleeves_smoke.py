"""Smoke tests for method sleeves (no network when using tiny synthetic hooks)."""

from __future__ import annotations

from trading_agent.export.mac_execute import ReadyOrder
from trading_agent.oms.pretrade import PretradeConfig, evaluate_pretrade
from trading_agent.oms.state import OmsStore
from trading_agent.sleeves.orb_vwap import OrbBacktestResult, format_orb_report
from trading_agent.sleeves.regime_premium import format_regime_report


def test_pretrade_buying_power_block(tmp_path):
    store = OmsStore(root=tmp_path / "oms")
    order = ReadyOrder(
        order_id="1",
        symbol="QQQ",
        action="ENTER",
        side="long",
        instrument="equity",
        strategy="x",
        setup_id="x",
        entry=100,
        stop=99,
        target=110,
        max_risk_dollars=500,
    )
    ok, reason = evaluate_pretrade(
        order,
        store,
        config=PretradeConfig(min_buying_power=1000, max_open_lots=10),
        buying_power=100,
    )
    assert not ok and reason == "insufficient_buying_power"


def test_format_orb_empty():
    r = OrbBacktestResult(
        symbols=["QQQ"],
        period="5d",
        trade_count=0,
        winners=0,
        losers=0,
        win_rate=0.0,
        total_pnl=0.0,
        expectancy=0.0,
        avg_r=0.0,
    )
    text = format_orb_report(r)
    assert "ORB" in text


def test_format_regime_minimal():
    d = {
        "period": "1y",
        "full": {"n": 0, "wr": 0, "exp": 0, "pnl": 0, "score": 0},
        "by_regime": {},
        "chop_only": {},
        "trend_only": {},
        "suggestion": "n/a",
    }
    assert "Premium" in format_regime_report(d)
