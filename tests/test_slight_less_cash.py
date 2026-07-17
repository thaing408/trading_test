"""Slight-less-cash env preset (A/B without changing shipped defaults)."""

from __future__ import annotations

import os

from trading_agent.cio.config import CIOConfig
from trading_agent.config import AgentConfig, RiskConfig


def test_risk_defaults_unchanged_without_env(monkeypatch):
    monkeypatch.delenv("TRADING_AGENT_SLIGHT_LESS_CASH", raising=False)
    monkeypatch.delenv("TRADING_AGENT_MIN_CONFIDENCE", raising=False)
    monkeypatch.delenv("TRADING_AGENT_MIN_QUALITY_B_EXCEPTION", raising=False)
    r = RiskConfig.from_env()
    assert r.min_confidence_score == 60.0
    assert r.min_quality_for_b_exception == 70.0
    assert r.prefer_a_tier_only is True


def test_slight_less_cash_preset(monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_SLIGHT_LESS_CASH", "1")
    monkeypatch.delenv("TRADING_AGENT_MIN_CONFIDENCE", raising=False)
    monkeypatch.delenv("TRADING_AGENT_MIN_QUALITY_B_EXCEPTION", raising=False)
    r = RiskConfig.from_env()
    assert r.min_confidence_score == 55.0
    assert r.min_quality_for_b_exception == 65.0
    assert r.prefer_a_tier_only is True  # still A-prefer


def test_individual_override_beats_preset(monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_SLIGHT_LESS_CASH", "1")
    monkeypatch.setenv("TRADING_AGENT_MIN_CONFIDENCE", "58")
    monkeypatch.setenv("TRADING_AGENT_MIN_QUALITY_B_EXCEPTION", "68")
    r = RiskConfig.from_env()
    assert r.min_confidence_score == 58.0
    assert r.min_quality_for_b_exception == 68.0


def test_agent_from_env_loads_risk(monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_SLIGHT_LESS_CASH", "1")
    monkeypatch.setenv("TRADING_AGENT_FIXTURE", "1")
    cfg = AgentConfig.from_env()
    assert cfg.risk.min_confidence_score == 55.0
    assert cfg.risk.min_quality_for_b_exception == 65.0


def test_cio_aligns_with_slight_less_cash(monkeypatch):
    monkeypatch.setenv("TRADING_AGENT_SLIGHT_LESS_CASH", "1")
    monkeypatch.delenv("TRADING_AGENT_CIO_MIN_CONFIDENCE", raising=False)
    c = CIOConfig.from_env()
    assert c.min_confidence == 55.0
