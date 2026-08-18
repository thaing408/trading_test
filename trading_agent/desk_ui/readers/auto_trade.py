"""Load auto_trade_book.json from known paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trading_agent.desk_ui.json_io import read_json_file
from trading_agent.desk_ui.paths import session_dir_for, sync_dir


@dataclass
class BookLoadResult:
    data: dict[str, Any]
    path: str | None
    error: str | None
    candidates: list[str]


def book_candidate_paths(trading_date: str | None = None) -> list[Path]:
    sync = sync_dir()
    paths = [
        sync / "auto_trade_book.json",
        Path.home() / ".grok" / "state" / "auto_trade_book.json",
    ]
    if trading_date:
        try:
            from datetime import date as date_cls

            td = date_cls.fromisoformat(trading_date)
            paths.insert(0, session_dir_for(td) / "auto_trade_book.json")
            paths.append(sync / "archive" / f"auto_trade_book_{trading_date}.json")
        except ValueError:
            pass
    # Prefer newest among existing — order is preference; loader picks mtime
    return paths


def load_auto_trade_book(
    *,
    trading_date: str | None = None,
    state: Path | None = None,
) -> BookLoadResult:
    """Load newest readable book among known targets."""
    candidates = book_candidate_paths(trading_date)
    if state is not None:
        # Test override: only under fixture state root
        root = Path(state)
        candidates = [
            root / "sync" / "auto_trade_book.json",
            root / "sessions" / (trading_date or "") / "auto_trade_book.json",
        ]
        if trading_date:
            candidates.append(
                root / "sync" / "archive" / f"auto_trade_book_{trading_date}.json"
            )

    best: dict[str, Any] | None = None
    best_path: Path | None = None
    best_mtime = -1.0
    last_err: str | None = None
    seen: list[str] = []

    for path in candidates:
        seen.append(str(path))
        if not path.is_file():
            continue
        data, err = read_json_file(path)
        if err:
            last_err = err
            continue
        if not isinstance(data, dict):
            last_err = "not_object"
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        if mtime >= best_mtime:
            best_mtime = mtime
            best = data
            best_path = path

    if best is None:
        return BookLoadResult(
            data={},
            path=None,
            error=last_err or "missing",
            candidates=seen,
        )
    return BookLoadResult(
        data=best,
        path=str(best_path) if best_path else None,
        error=None,
        candidates=seen,
    )
