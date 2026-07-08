"""Post play suggestions to a Discord webhook."""

from __future__ import annotations

from typing import Any, Callable

import requests

from trading_agent.discord.formatter import chunk_message

HttpPoster = Callable[[str, dict[str, Any]], Any]


class DiscordPostError(RuntimeError):
    """Raised when Discord delivery cannot proceed."""


def post_to_discord(
    content: str,
    webhook_url: str | None,
    *,
    username: str | None = None,
    poster: HttpPoster | None = None,
) -> list[dict[str, Any]]:
    """POST content to Discord, chunking when needed. Returns per-chunk results."""
    if not webhook_url:
        raise DiscordPostError(
            "DISCORD_WEBHOOK_URL is not set. "
            "Export the webhook URL or run with --dry-run / --no-discord."
        )

    chunks = chunk_message(content)
    results: list[dict[str, Any]] = []
    post_fn = poster or _default_poster

    for index, chunk in enumerate(chunks, start=1):
        payload: dict[str, Any] = {"content": chunk}
        if username:
            payload["username"] = username
        response = post_fn(webhook_url, payload)
        results.append(
            {
                "chunk": index,
                "total_chunks": len(chunks),
                "status_code": getattr(response, "status_code", None),
                "ok": getattr(response, "ok", None),
                "text": getattr(response, "text", str(response)),
            }
        )
    return results


def _default_poster(webhook_url: str, payload: dict[str, Any]) -> requests.Response:
    response = requests.post(webhook_url, json=payload, timeout=30)
    if response.status_code >= 400:
        raise DiscordPostError(
            f"Discord webhook returned {response.status_code}: {response.text[:200]}"
        )
    return response