"""Discord delivery configuration (webhook or bot channel)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

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

    def with_channel(self, channel_id: str | None) -> "DiscordConfig":
        """Copy config pointing at a different bot channel (webhook unchanged)."""
        cid = (channel_id or "").strip() or self.channel_id
        return DiscordConfig(
            webhook_url=self.webhook_url if not cid else None,
            bot_token=self.bot_token,
            channel_id=cid,
        )

    @classmethod
    def income_channel_from_env(cls) -> "DiscordConfig | None":
        """Bot config for income plays, or None if DISCORD_INCOME_CHANNEL_ID unset."""
        load_project_env()
        channel = (
            os.getenv("DISCORD_INCOME_CHANNEL_ID")
            or os.getenv("DISCORD_INCOME_PLAYS_CHANNEL_ID")
            or ""
        ).strip()
        if not channel:
            return None
        base = cls.from_env()
        token = base.bot_token or os.getenv("DISCORD_BOT_TOKEN") or None
        if not token:
            return None
        # Force bot channel (do not use production webhook for income)
        return DiscordConfig(webhook_url=None, bot_token=token, channel_id=channel)

    @classmethod
    def tv_ta_channel_from_env(cls) -> "DiscordConfig | None":
        """Bot config for TradingView TA research posts.

        Channel: DISCORD_TV_TA_CHANNEL_ID (default 1539794451612958761).
        Uses bot token only (never the production webhook).
        """
        load_project_env()
        # Mac desk secrets live here (same as journal / consumer)
        try:
            from dotenv import load_dotenv

            grok_discord = Path.home() / ".grok" / "discord.env"
            grok_agent = Path.home() / ".grok" / "trading-agent.env"
            if grok_discord.is_file():
                load_dotenv(grok_discord, override=False)
            if grok_agent.is_file():
                load_dotenv(grok_agent, override=False)
        except Exception:
            pass
        channel = (os.getenv("DISCORD_TV_TA_CHANNEL_ID") or "1539794451612958761").strip()
        if not channel:
            return None
        base = cls.from_env()
        token = (
            base.bot_token
            or os.getenv("DISCORD_BOT_TOKEN")
            or os.getenv("DISCORD_TOKEN")
            or None
        )
        if not token:
            return None
        return DiscordConfig(webhook_url=None, bot_token=token, channel_id=channel)
