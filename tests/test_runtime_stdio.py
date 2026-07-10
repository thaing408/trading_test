"""Tests for Windows-safe console output."""

from __future__ import annotations

import io

from trading_agent.runtime.stdio import safe_print, safe_write


def test_safe_print_writes_to_buffer():
    buffer = io.StringIO()
    safe_print("Phase scope: intelligence -> preopen", file=buffer)
    assert "intelligence -> preopen" in buffer.getvalue()


def test_safe_write_logs_without_raising():
    buffer = io.StringIO()
    safe_write(buffer, "Bias: Bullish — risk-on")
    assert "Bullish" in buffer.getvalue()