"""Index session directory files for desk-ui /session."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def list_session_files(
    trading_date: date | str,
    *,
    state: Path | None = None,
    max_files: int = 200,
) -> dict[str, Any]:
    """Return file index under sessions/YYYY-MM-DD (read-only)."""
    td = (
        trading_date
        if isinstance(trading_date, date)
        else date.fromisoformat(str(trading_date)[:10])
    )
    root = Path(state) if state is not None else Path.home() / ".trading_agent"
    session = root / "sessions" / td.isoformat()
    out: dict[str, Any] = {
        "trading_date": td.isoformat(),
        "session_dir": str(session),
        "exists": session.is_dir(),
        "files": [],
        "notes": [],
    }
    if not session.is_dir():
        out["notes"].append("session directory missing")
        return out

    rows: list[dict[str, Any]] = []
    try:
        paths = sorted(session.rglob("*"), key=lambda p: str(p).lower())
    except OSError as exc:
        out["notes"].append(f"list_error:{exc}")
        return out

    for p in paths:
        if not p.is_file():
            continue
        # Skip giant binary / cache noise
        name = p.name.lower()
        if name.endswith((".pyc", ".png", ".jpg", ".jpeg", ".gif", ".mp4")):
            continue
        try:
            st = p.stat()
            mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
            size = int(st.st_size)
        except OSError:
            mtime = None
            size = None
        rows.append(
            {
                "path": str(p),
                "rel": _rel(p, session),
                "size": size,
                "mtime_iso": mtime,
            }
        )
        if len(rows) >= max_files:
            out["notes"].append(f"truncated_at_{max_files}")
            break
    out["files"] = rows
    return out
