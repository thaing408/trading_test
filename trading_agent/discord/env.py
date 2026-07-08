"""Load environment variables from trading_agent and researcher .env files."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

RESEARCHER_ENV = Path(r"C:\Personal\Scripts\researcher\.env")


def load_project_env() -> list[str]:
    """Load .env files in priority order; returns paths loaded."""
    candidates: list[Path] = []
    explicit = os.getenv("TRADING_AGENT_ENV_FILE", "").strip()
    if explicit:
        candidates.append(Path(explicit))
    candidates.extend(
        [
            Path.cwd() / ".env",
            Path(__file__).resolve().parents[2] / ".env",
            RESEARCHER_ENV,
        ]
    )

    loaded: list[str] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen or not path.is_file():
            continue
        seen.add(key)
        load_dotenv(path, override=False)
        loaded.append(str(path))
    return loaded