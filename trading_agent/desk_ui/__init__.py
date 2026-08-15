"""Auto-trade desk investigation surface (local file readers + CLI).

PR1 ships pure snapshot assembly and ``desk-status`` CLI (no HTTP).
"""

from __future__ import annotations

from trading_agent.desk_ui.phase import PhaseStatus, current_phase_status
from trading_agent.desk_ui.snapshot import DeskSnapshot, assemble_snapshot

__all__ = [
    "DeskSnapshot",
    "PhaseStatus",
    "assemble_snapshot",
    "current_phase_status",
]
