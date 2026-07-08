"""Load completed trade records from fixtures or files."""

from __future__ import annotations

import json
from pathlib import Path

from trading_agent.performance.models import CompletedTrade

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_trades(path: str | None, fixture_mode: bool) -> list[CompletedTrade]:
    file_path = Path(path) if path else FIXTURE_DIR / "completed_trades.json"
    if fixture_mode and not path:
        file_path = FIXTURE_DIR / "completed_trades.json"
    data = _load_json(file_path)
    return [CompletedTrade(**t) for t in data.get("trades", [])]


def load_history(path: str | None, fixture_mode: bool) -> list[CompletedTrade]:
    file_path = Path(path) if path else FIXTURE_DIR / "trade_history.json"
    if fixture_mode and not path:
        file_path = FIXTURE_DIR / "trade_history.json"
    if not file_path.exists():
        return []
    data = _load_json(file_path)
    return [CompletedTrade(**t) for t in data.get("trades", [])]