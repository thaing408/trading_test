"""Format and chunk messages for Discord webhook limits."""

from __future__ import annotations

DISCORD_CONTENT_LIMIT = 2000


def chunk_message(text: str, limit: int = DISCORD_CONTENT_LIMIT) -> list[str]:
    """Split text into Discord-safe chunks, preferring line boundaries."""
    text = text.strip()
    if not text:
        return [""]
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(line) > limit:
            if current:
                chunks.append(current.rstrip())
                current = ""
            start = 0
            while start < len(line):
                chunks.append(line[start : start + limit].rstrip())
                start += limit
            continue
        if len(current) + len(line) > limit:
            chunks.append(current.rstrip())
            current = line
        else:
            current += line
    if current:
        chunks.append(current.rstrip())
    return [c for c in chunks if c]