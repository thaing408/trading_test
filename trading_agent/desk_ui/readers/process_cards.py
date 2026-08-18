"""Process trade cards under ~/.trading_agent/process/."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from trading_agent.desk_ui.json_io import read_json_file
from trading_agent.desk_ui.paths import process_cards_path


def load_process_cards(
    trading_date: date,
    *,
    state: Path | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    if state is not None:
        path = Path(state) / "process" / f"{trading_date.isoformat()}.json"
    else:
        path = process_cards_path(trading_date)

    data, err = read_json_file(path)
    if err or not isinstance(data, dict):
        return [], err

    cards = data.get("cards") or data.get("trade_cards") or data.get("items")
    if isinstance(cards, list):
        return [c for c in cards if isinstance(c, dict)], None
    # Whole doc as single card bag
    if data:
        return [data], None
    return [], None
