"""Suite defaults: WR desk gates off unless a test turns them on."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _wr_desk_off_by_default(monkeypatch):
    if os.getenv("TRADING_AGENT_WR_DESK_TEST") == "1":
        return
    monkeypatch.setenv("TRADING_AGENT_WR_DESK", "0")
