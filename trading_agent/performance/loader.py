"""Load completed trade records from fixtures or files."""

from __future__ import annotations

import json
from pathlib import Path

from trading_agent.performance.models import CompletedTrade

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
FIXTURE_TRADES_REL = "fixture/completed_trades.json"
FIXTURE_HISTORY_REL = "fixture/trade_history.json"


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def resolve_trades_path(path: str | None, fixture_mode: bool) -> tuple[Path | None, str]:
    """
    Resolve trades file path and a stable source label.

    Live mode (fixture_mode=False) never silently falls back to demo fixtures.
    """
    if path:
        return Path(path), str(path)
    if fixture_mode:
        return FIXTURE_DIR / "completed_trades.json", FIXTURE_TRADES_REL
    return None, "none"


def resolve_history_path(path: str | None, fixture_mode: bool) -> tuple[Path | None, str]:
    if path:
        return Path(path), str(path)
    if fixture_mode:
        return FIXTURE_DIR / "trade_history.json", FIXTURE_HISTORY_REL
    return None, "none"


def load_trades(path: str | None, fixture_mode: bool) -> list[CompletedTrade]:
    file_path, _label = resolve_trades_path(path, fixture_mode)
    if file_path is None:
        return []
    if not file_path.exists():
        if fixture_mode:
            return []
        return []
    data = _load_json(file_path)
    return [CompletedTrade(**t) for t in data.get("trades", [])]


def load_history(path: str | None, fixture_mode: bool) -> list[CompletedTrade]:
    file_path, _label = resolve_history_path(path, fixture_mode)
    if file_path is None or not file_path.exists():
        return []
    data = _load_json(file_path)
    return [CompletedTrade(**t) for t in data.get("trades", [])]
