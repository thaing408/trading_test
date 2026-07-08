"""Discord webhook configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class DiscordConfig:
    webhook_url: str | None = None

    @classmethod
    def from_env(cls) -> "DiscordConfig":
        return cls(webhook_url=os.getenv("DISCORD_WEBHOOK_URL") or None)

    def require_webhook(self) -> str:
        from trading_agent.discord.poster import DiscordPostError

        if not self.webhook_url:
            raise DiscordPostError(
                "DISCORD_WEBHOOK_URL is not set. "
                "Export the webhook URL or run with --dry-run / --no-discord."
            )
        return self.webhook_url