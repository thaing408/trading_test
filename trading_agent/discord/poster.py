"""Post play suggestions to Discord via webhook or bot channel."""

from __future__ import annotations

from typing import Any, Callable

import requests

from trading_agent.discord.config import DiscordConfig
from trading_agent.discord.formatter import chunk_message

HttpPoster = Callable[[str, dict[str, Any], dict[str, str]], Any]


class DiscordPostError(RuntimeError):
    """Raised when Discord delivery cannot proceed."""


def post_message(
    content: str,
    config: DiscordConfig,
    *,
    username: str | None = None,
    poster: HttpPoster | None = None,
) -> list[dict[str, Any]]:
    """Deliver content using webhook (preferred) or bot channel."""
    if config.webhook_url:
        return post_to_discord(
            content,
            config.webhook_url,
            username=username,
            poster=poster,
        )
    if config.bot_token and config.channel_id:
        return post_to_discord_channel(
            content,
            config.bot_token,
            config.channel_id,
            poster=poster,
        )
    raise DiscordPostError(
        "Discord not configured. Set DISCORD_WEBHOOK_URL or "
        "DISCORD_TOKEN + DISCORD_CHANNEL_ID (see researcher .env)."
    )


def post_to_discord(
    content: str,
    webhook_url: str | None,
    *,
    username: str | None = None,
    poster: HttpPoster | None = None,
) -> list[dict[str, Any]]:
    """POST content to a Discord webhook, chunking when needed."""
    if not webhook_url:
        raise DiscordPostError("DISCORD_WEBHOOK_URL is not set.")

    chunks = chunk_message(content)
    results: list[dict[str, Any]] = []
    post_fn = poster or _default_webhook_poster

    for index, chunk in enumerate(chunks, start=1):
        payload: dict[str, Any] = {"content": chunk}
        if username:
            payload["username"] = username
        response = post_fn(webhook_url, payload, {})
        results.append(_result_dict(index, len(chunks), response, mode="webhook"))
    return results


def post_to_discord_channel(
    content: str,
    bot_token: str,
    channel_id: str,
    *,
    poster: HttpPoster | None = None,
) -> list[dict[str, Any]]:
    """POST content to a Discord channel via bot token."""
    if not bot_token or not channel_id:
        raise DiscordPostError("DISCORD_TOKEN and DISCORD_CHANNEL_ID are required.")

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json",
    }
    chunks = chunk_message(content)
    results: list[dict[str, Any]] = []
    post_fn = poster or _default_channel_poster

    for index, chunk in enumerate(chunks, start=1):
        response = post_fn(url, {"content": chunk}, headers)
        results.append(_result_dict(index, len(chunks), response, mode="bot_channel"))
    return results


def _result_dict(index: int, total: int, response: Any, *, mode: str) -> dict[str, Any]:
    return {
        "chunk": index,
        "total_chunks": total,
        "mode": mode,
        "status_code": getattr(response, "status_code", None),
        "ok": getattr(response, "ok", None),
        "text": getattr(response, "text", str(response)),
    }


def _default_webhook_poster(
    webhook_url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
) -> requests.Response:
    response = requests.post(webhook_url, json=payload, headers=headers, timeout=30)
    if response.status_code >= 400:
        raise DiscordPostError(
            f"Discord webhook returned {response.status_code}: {response.text[:200]}"
        )
    return response


def _default_channel_poster(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
) -> requests.Response:
    response = requests.post(url, json=payload, headers=headers, timeout=30)
    if response.status_code >= 400:
        raise DiscordPostError(
            f"Discord channel post returned {response.status_code}: {response.text[:200]}"
        )
    return response