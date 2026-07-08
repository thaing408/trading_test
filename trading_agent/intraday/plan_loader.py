"""Load Daily Trading Plan context and open positions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from trading_agent.intraday.models import OpenPosition

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def load_positions(path: str | None, fixture_mode: bool) -> List[OpenPosition]:
    file_path = Path(path) if path else FIXTURE_DIR / "open_positions.json"
    if fixture_mode and not path:
        file_path = FIXTURE_DIR / "open_positions.json"
    with file_path.open(encoding="utf-8") as f:
        data = json.load(f)
    return [OpenPosition(**p) for p in data.get("positions", [])]


def load_plan_context(path: str | None, fixture_mode: bool) -> dict:
    file_path = Path(path) if path else FIXTURE_DIR / "daily_plan_context.json"
    if fixture_mode and not path:
        file_path = FIXTURE_DIR / "daily_plan_context.json"
    with file_path.open(encoding="utf-8") as f:
        return json.load(f)