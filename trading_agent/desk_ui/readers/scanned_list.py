"""Load scanned_list / auto_trade_scan_symbols."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trading_agent.desk_ui.json_io import read_json_file
from trading_agent.export.scanned_list import empty_scanned_list, load_scanned_list


@dataclass
class ScannedLoadResult:
    data: dict[str, Any]
    path: str | None
    error: str | None


def load_scanned(
    *,
    trading_date: str | None = None,
    sync_dir: Path | None = None,
    state: Path | None = None,
) -> ScannedLoadResult:
    if state is not None:
        root = Path(state)
        for name in ("scanned_list.json", "auto_trade_scan_symbols.json"):
            path = root / "sync" / name
            data, err = read_json_file(path)
            if err is None and isinstance(data, dict):
                return ScannedLoadResult(data=data, path=str(path), error=None)
        empty = empty_scanned_list(trading_date=trading_date)
        return ScannedLoadResult(data=empty, path=None, error="missing")

    try:
        data = load_scanned_list(
            sync_dir=sync_dir,
            max_age_hours=None,
            require_today=False,
        )
    except Exception as exc:
        empty = empty_scanned_list(trading_date=trading_date)
        return ScannedLoadResult(data=empty, path=None, error=str(exc))

    if not data:
        empty = empty_scanned_list(trading_date=trading_date)
        return ScannedLoadResult(data=empty, path=None, error="missing")
    return ScannedLoadResult(data=data, path=None, error=None)
