"""Quarterly Theory–style open-window mechanical model (objective proxies).

Source inspiration: discretionary QT/SSMT journals (e.g. TradeZella 9:30–9:50 ET).
This package codifies *testable* proxies — not full ICT discretionary labeling.
"""

from trading_agent.qt.model import (
    QtModelConfig,
    QtSignal,
    QtSessionBrief,
    format_qt_brief,
    run_qt_model,
    signals_to_auto_trade_entries,
)

__all__ = [
    "QtModelConfig",
    "QtSignal",
    "QtSessionBrief",
    "format_qt_brief",
    "run_qt_model",
    "signals_to_auto_trade_entries",
]
