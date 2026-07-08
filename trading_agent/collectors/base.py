"""Base utilities for data collectors."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def load_fixture(name: str) -> Dict[str, Any]:
    path = FIXTURE_DIR / name
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def safe_fetch(fetcher, fallback_data: Dict[str, Any], errors: list) -> Dict[str, Any]:
    try:
        return fetcher()
    except Exception as exc:  # noqa: BLE001 - graceful degradation
        errors.append(str(exc))
        return fallback_data