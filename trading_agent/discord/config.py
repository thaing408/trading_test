"""Discord delivery configuration (webhook or bot channel)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from trading_agent.discord.env import load_project_env


@dataclass
class DiscordConfig:
    webhook_url: str | None = None
    bot_token: str | None = None
    channel_id: str | None = None

    @classmethod
    def from_env(cls) -> "DiscordConfig":
        load_project_env()
        return cls(
            webhook_url=os.getenv("DISCORD_WEBHOOK_URL") or None,
            bot_token=os.getenv("DISCORD_TOKEN") or None,
            channel_id=os.getenv("DISCORD_CHANNEL_ID") or None,
        )

    def has_delivery(self) -> bool:
        if self.webhook_url:
            return True
        return bool(self.bot_token and self.channel_id)

    def delivery_mode(self) -> str:
        if self.webhook_url:
            return "webhook"
        if self.bot_token and self.channel_id:
            return "bot_channel"
        return "none"