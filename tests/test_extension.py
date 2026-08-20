"""Qullamaggie / Muninn ADR extension dials."""

from __future__ import annotations

from trading_agent.analysis.extension import (
    BUCKET_025_050,
    BUCKET_050_100,
    BUCKET_GT_100,
    BUCKET_LT_025,
    adr_bucket,
    apply_extension_to_entry,
    average_daily_range,
    compute_adr_used,
    discord_extension_line,
    enrich_entry_row_from_bars,
    evaluate_extension,
    size_cut_multiplier,
)


def test_average_daily_range_dollars():
    highs = [10, 12, 11, 13]
    lows = [8, 10, 9, 11]
    # ranges: 2,2,2,2 → mean 2
    assert average_daily_range(highs, lows, lookback=4) == 2.0
    assert average_daily_range(highs, lows, lookback=2) == 2.0


def test_adr_used_long_and_short():
    # ADR=10, long entry 105 from low 100 → 0.5
    assert compute_adr_used(
        entry=105, side="Bullish", session_low=100, session_high=120, adr=10
    ) == 0.5
    # short entry 110 from high 120 → 1.0
    assert compute_adr_used(
        entry=110, side="Bearish", session_low=100, session_high=120, adr=10
    ) == 1.0
    assert compute_adr_used(
        entry=105, side="PUT", session_low=100, session_high=120, adr=10
    ) == 1.5  # (120 - 105) / 10


def test_adr_buckets():
    assert adr_bucket(0.1) == BUCKET_LT_025
    assert adr_bucket(0.33) == BUCKET_025_050
    assert adr_bucket(0.68) == BUCKET_050_100
    assert adr_bucket(1.0) == BUCKET_050_100
    assert adr_bucket(1.2) == BUCKET_GT_100
    assert adr_bucket(None) is None


def test_size_cut_flag_off_vs_on():
    assert size_cut_multiplier(BUCKET_LT_025, apply=False) == 1.0
    assert size_cut_multiplier(BUCKET_GT_100, apply=False) == 1.0
    assert size_cut_multiplier(BUCKET_LT_025, apply=True) == 0.5
    assert size_cut_multiplier(BUCKET_GT_100, apply=True) == 0.5
    assert size_cut_multiplier(BUCKET_025_050, apply=True) == 1.0
    assert size_cut_multiplier(BUCKET_050_100, apply=True) == 1.0


def test_evaluate_and_apply_size_cut(monkeypatch):
    monkeypatch.delenv("TRADING_AGENT_ADR_EXTENSION", raising=False)
    res = evaluate_extension(
        entry=102,
        side="Bullish",
        session_low=100,
        session_high=115,
        adr=10,
        apply_size=False,
    )
    assert res.adr_used == 0.2
    assert res.adr_bucket == BUCKET_LT_025
    assert "0.20" in res.extension_note
    assert res.size_mult == 1.0
    assert res.applied_size_cut is False

    row = {
        "symbol": "TEST",
        "entry": 102,
        "side": "Bullish",
        "max_risk_dollars": 200.0,
        "quantity": 2,
        "notes": "",
    }
    apply_extension_to_entry(row, res)
    assert row["adr_used"] == 0.2
    assert row["adr_bucket"] == BUCKET_LT_025
    assert row["max_risk_dollars"] == 200.0  # flag off — no cut

    res2 = evaluate_extension(
        entry=102,
        side="Bullish",
        session_low=100,
        session_high=115,
        adr=10,
        apply_size=True,
    )
    row2 = {
        "symbol": "TEST",
        "entry": 102,
        "side": "Bullish",
        "max_risk_dollars": 200.0,
        "quantity": 2,
        "notes": "",
    }
    apply_extension_to_entry(row2, res2)
    assert row2["max_risk_dollars"] == 100.0
    assert row2["quantity"] == 1
    assert "adr_size_cut" in row2["notes"]


def test_enrich_from_bars_band():
    # Last bar high/low = session; prior ranges define ADR
    highs = [110 + i for i in range(20)]  # rising
    lows = [100 + i for i in range(20)]  # range always 10
    # session from last bar: high=129, low=119; entry mid of band for long from low
    # entry = 119 + 5 = 124 → adr_used = 5/10 = 0.5
    row = {
        "symbol": "X",
        "entry": 124.0,
        "side": "Bullish",
        "max_risk_dollars": 100.0,
        "quantity": 1,
    }
    out = enrich_entry_row_from_bars(row, highs=highs, lows=lows, apply_size=False)
    assert out["adr"] == 10.0
    assert out["adr_used"] == 0.5
    assert out["adr_bucket"] == BUCKET_050_100
    assert out["max_risk_dollars"] == 100.0


def test_discord_extension_line():
    assert "0.41" in discord_extension_line(
        {"adr_used": 0.41, "adr_bucket": "025_050", "extension_note": "ADR used 0.41 (early band)"}
    )
    assert discord_extension_line({}) == ""
