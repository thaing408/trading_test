"""Safe console I/O for Windows Task Scheduler (legacy code pages)."""

from __future__ import annotations

import sys
from typing import TextIO


def configure_stdio() -> None:
    """Prefer UTF-8 stdout/stderr; fall back safely on older hosts."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError, AttributeError):
            pass


def safe_print(message: str, *, file: TextIO | None = None, flush: bool = True) -> None:
    """Print without crashing when the console cannot encode Unicode."""
    target = file or sys.stdout
    try:
        print(message, file=target, flush=flush)
    except UnicodeEncodeError:
        encoding = getattr(target, "encoding", None) or "ascii"
        print(message.encode(encoding, errors="replace").decode(encoding), file=target, flush=flush)


def safe_write(handle: TextIO | None, message: str) -> None:
    """Write to session log and console; never raise on encoding."""
    safe_print(message)
    if handle:
        handle.write(message + "\n")
        handle.flush()