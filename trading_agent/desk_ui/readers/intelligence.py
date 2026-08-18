"""Load session intelligence.json for market context table."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from trading_agent.desk_ui.json_io import read_json_file
from trading_agent.desk_ui.paths import session_dir_for


@dataclass
class IntelligenceLoadResult:
    data: dict[str, Any]
    path: str | None
    error: str | None


def load_intelligence(
    trading_date: date,
    *,
    state: Path | None = None,
) -> IntelligenceLoadResult:
    if state is not None:
        path = Path(state) / "sessions" / trading_date.isoformat() / "intelligence.json"
    else:
        path = session_dir_for(trading_date) / "intelligence.json"

    if not path.is_file():
        return IntelligenceLoadResult(data={}, path=str(path), error="missing")

    data, err = read_json_file(path)
    if err or not isinstance(data, dict):
        return IntelligenceLoadResult(data={}, path=str(path), error=err or "not_object")
    return IntelligenceLoadResult(data=data, path=str(path), error=None)
