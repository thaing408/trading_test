"""Safe concurrent file reads with one retry on truncated JSON."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Tuple


def read_json_file(
    path: Path,
    *,
    retry_ms: float = 75.0,
) -> Tuple[Any | None, str | None]:
    """Return (data, error). On parse failure retry once after retry_ms."""
    p = Path(path)
    if not p.is_file():
        return None, "missing"

    def _once() -> Tuple[Any | None, str | None]:
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as exc:
            return None, f"os_error:{exc}"
        if not text.strip():
            return None, "empty"
        try:
            return json.loads(text), None
        except json.JSONDecodeError as exc:
            return None, f"json_error:{exc}"

    data, err = _once()
    if err is None:
        return data, None
    if err.startswith("json_error") or err == "empty":
        time.sleep(max(0.0, retry_ms) / 1000.0)
        data2, err2 = _once()
        if err2 is None:
            return data2, None
        return None, err2
    return None, err
