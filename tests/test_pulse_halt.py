"""Named Scalp Pulse halt card — must list which tickers lost."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from trading_agent.scalp.pulse_halt import (
    format_session_halt_card,
    load_ledger,
    maybe_post_session_halt,
    record_pulse_close,
    sleeve_halted,
)

PT = ZoneInfo("America/Los_Angeles")
DAY = datetime(2026, 8, 18, 7, 29, tzinfo=PT)


def test_halt_card_names_tickers(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_PULSE_LEDGER", str(tmp_path / "pulse.json"))
    ledger = tmp_path / "pulse.json"
    record_pulse_close("NVDA", side="PUT", pnl=-30.0, path=ledger, now=DAY)
    led = record_pulse_close("AMD", side="CALL", pnl=-25.0, path=ledger, now=DAY)
    assert sleeve_halted(led)
    card = format_session_halt_card(led)
    assert "Session HALTED" in card
    assert "NVDA PUT" in card
    assert "AMD CALL" in card
    assert "NVDA: trips=1" in card
    assert "AMD: trips=1" in card
    assert "sleeve trips=2 W=0 L=2" in card
    assert "all tickers blocked" in card


def test_one_loss_does_not_halt(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_PULSE_LEDGER", str(tmp_path / "pulse.json"))
    ledger = tmp_path / "pulse.json"
    led = record_pulse_close("QQQ", side="CALL", pnl=-10.0, path=ledger, now=DAY)
    assert not sleeve_halted(led)
    card = format_session_halt_card(led)
    assert "session open" in card
    assert "QQQ CALL" in card


def test_maybe_post_once(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_PULSE_LEDGER", str(tmp_path / "pulse.json"))
    ledger = tmp_path / "pulse.json"
    record_pulse_close("NVDA", side="PUT", pnl=-1.0, path=ledger, now=DAY)
    led = record_pulse_close("AMD", side="PUT", pnl=-1.0, path=ledger, now=DAY)
    first = maybe_post_session_halt(led, path=ledger, post=False)
    assert first["reason"] == "dry_run"
    led.halt_posted = True
    again = maybe_post_session_halt(led, path=ledger, post=False)
    assert again["reason"] == "already_posted"


def test_ledger_rolls_next_day(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_PULSE_LEDGER", str(tmp_path / "pulse.json"))
    ledger = tmp_path / "pulse.json"
    record_pulse_close("NVDA", side="PUT", pnl=-1.0, path=ledger, now=DAY)
    nxt = datetime(2026, 8, 19, 6, 30, tzinfo=PT)
    led = load_ledger(ledger, day=nxt.date().isoformat())
    assert led.closes == []
    assert not sleeve_halted(led)
