"""Unit tests for intraday alert triggers."""

from trading_agent.intraday.config import IntradayRiskConfig
from trading_agent.intraday.decisions.alerts import detect_alerts
from trading_agent.intraday.decisions.evaluator import evaluate_position
from trading_agent.intraday.decisions.guards import check_averaging_down
from trading_agent.intraday.models import (
    OpenPosition,
    SessionSnapshot,
    SessionSynthesis,
    SymbolSessionData,
)


def _position(**kw):
    defaults = {
        "symbol": "AAPL",
        "strategy": "Long Call",
        "entry_price": 225.0,
        "stop_loss": 220.0,
        "profit_target": 235.0,
        "strike_prices": [230.0],
        "expiration": "2026-08-15",
    }
    defaults.update(kw)
    return OpenPosition(**defaults)


def _snapshot(symbol="AAPL", price=218.0, news=None, prior="bullish", regime="bullish"):
    return SessionSnapshot(
        source="test",
        market_regime=regime,
        prior_regime=prior,
        vix=18.0,
        vix_change_pct=0.0,
        breadth_advancers=4,
        breadth_decliners=4,
        breadth_ratio=0.5,
        sector_leaders=["XLK"],
        sector_laggards=["XLE"],
        symbols={
            symbol: SymbolSessionData(
                symbol=symbol,
                price=price,
                change_pct=-2.0,
                vwap=222.0,
                volume=1_000_000,
                relative_volume=1.0,
                support=215.0,
                resistance=225.0,
                trend="downtrend",
                momentum="decelerating",
                iv=30.0,
                iv_change_pct=0.0,
                open_interest=5000,
                oi_change_pct=0.0,
                delta=0.5,
                gamma=0.01,
                theta=-0.05,
                vega=0.1,
                options_flow_bias="bearish",
            )
        },
        breaking_news=news or [],
    )


def _synthesis(regime_shift=False):
    return SessionSynthesis(
        regime_shift=regime_shift,
        regime_description="test",
        observations=[],
        risk_environment="normal",
        session_score=50.0,
    )


def test_stop_loss_triggers_exit():
    pos = _position()
    snap = _snapshot(price=218.0)
    rec = evaluate_position(pos, snap, _synthesis(), IntradayRiskConfig())
    assert rec.action == "Exit"
    assert any(a.alert_type == "stop_loss_triggered" for a in rec.alerts)


def test_thesis_invalidating_news_triggers_exit():
    pos = _position(symbol="TSLA")
    snap = _snapshot(
        symbol="TSLA",
        price=248.0,
        news=["[TSLA] Analyst downgrade: demand concerns worsen"],
    )
    rec = evaluate_position(pos, snap, _synthesis(), IntradayRiskConfig())
    assert rec.action == "Exit"
    assert any(a.alert_type == "thesis_invalidated" for a in rec.alerts)


def test_no_scale_in_when_averaging_down_forbidden():
    pos = _position(allows_averaging_down=False)
    snap = _snapshot(price=210.0)
    snap.symbols["AAPL"].trend = "uptrend"
    snap.symbols["AAPL"].momentum = "accelerating"
    rec = evaluate_position(pos, snap, _synthesis(), IntradayRiskConfig())
    assert rec.action != "Scale In"
    assert not check_averaging_down(pos, 210.0)


def test_zero_quantity_produces_no_alerts():
    pos = _position(quantity=0)
    snap = _snapshot(price=300.0)
    synth = _synthesis(regime_shift=True)
    alerts = detect_alerts(pos, snap, synth, IntradayRiskConfig())
    assert alerts == []


def test_missing_price_does_not_force_stop_loss():
    pos = _position(current_price=0.0, entry_price=0.0, stop_loss=10.0, profit_target=20.0)
    snap = _snapshot(price=0.0)
    # Empty symbols map → no quote
    snap.symbols = {}
    synth = _synthesis()
    alerts = detect_alerts(pos, snap, synth, IntradayRiskConfig())
    assert not any(a.alert_type == "stop_loss_triggered" for a in alerts)


def test_regime_shift_alert():
    pos = _position()
    snap = _snapshot(prior="bullish", regime="bearish")
    synth = _synthesis(regime_shift=True)
    alerts = detect_alerts(pos, snap, synth, IntradayRiskConfig())
    assert any(a.alert_type == "regime_shift" for a in alerts)