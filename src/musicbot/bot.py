"""Discord music bot — entry point."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from . import __version__
from .commands import Music
from .config import Settings
from .errors import MusicBotError
from .player import PlayerManager
from .source import YTDLSource
from .ui import Embeds, respond

log = logging.getLogger(__name__)

_SYNC_CACHE_FILE = Path(".command_sync.cache")


class MusicBot(commands.Bot):
    """The Discord music bot application."""

    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        intents.voice_states = True

        activity = (
            discord.Game(name=settings.activity_name)
            if settings.activity_name
            else None
        )

        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
            allowed_mentions=discord.AllowedMentions(
                everyone=False, users=True, roles=False
            ),
            activity=activity,
            status=discord.Status.online,
        )
        self.settings = settings
        self.players = PlayerManager(self)

    async def setup_hook(self) -> None:
        await self.add_cog(Music(self))
        current = self._tree_hash()
        if self._read_synced_hash() == current:
            log.info("Application commands unchanged; skipping sync")
            return
        synced = await self.tree.sync()
        log.info("Synced %d application commands", len(synced))
        _SYNC_CACHE_FILE.write_text(current, encoding="utf-8")

    def _tree_hash(self) -> str:
        signatures: list[dict[str, Any]] = []
        for cmd in self.tree.get_commands():
            if not isinstance(cmd, app_commands.Command):
                continue
            signatures.append(
                {
                    "name": cmd.name,
                    "description": cmd.description,
                    "guild_only": cmd.guild_only,
                    "default_permissions": (
                        cmd.default_permissions.value
                        if cmd.default_permissions
                        else None
                    ),
                    "parameters": [
                        {
                            "name": p.name,
                            "description": p.description,
                            "type": p.type.value,
                            "required": p.required,
                            "min_value": p.min_value,
                            "max_value": p.max_value,
                            "choices": [
                                (c.name, c.value) for c in (p.choices or [])
                            ],
                        }
                        for p in cmd.parameters
                    ],
                }
            )
        signatures.sort(key=lambda s: s["name"])
        payload = json.dumps(signatures, default=str, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _read_synced_hash() -> str | None:
        try:
            return _SYNC_CACHE_FILE.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return None

    async def on_ready(self) -> None:
        assert self.user is not None
        log.info(
            "Logged in as %s (id=%s) — version %s",
            self.user,
            self.user.id,
            __version__,
        )

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if self.user and member.id == self.user.id:
            if before.channel and not after.channel:
                player = self.players.get_existing(member.guild.id)
                if player is not None:
                    await player.stop()
            return

        player = self.players.get_existing(member.guild.id)
        if player is None or player.voice_client is None:
            return
        bot_channel = player.voice_client.channel
        if bot_channel not in (before.channel, after.channel):
            return
        if player.human_listeners():
            player.cancel_disconnect_grace()
        else:
            player.schedule_disconnect_if_empty()

    async def close(self) -> None:
        log.info("Shutting down — disconnecting all players")
        await self.players.shutdown()
        await super().close()


def _configure_logging(level: str) -> None:
    log_level = getattr(logging, level, logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()
    root.addHandler(handler)
    logging.getLogger("yt_dlp").setLevel(logging.WARNING)
    logging.getLogger("ffmpeg").setLevel(logging.WARNING)


def main() -> None:
    settings = Settings.load()
    _configure_logging(settings.log_level)
    YTDLSource.configure(settings)

    bot = MusicBot(settings)

    @bot.tree.error
    async def on_app_command_error(
        interaction: discord.Interaction,
        error: Exception,
    ) -> None:
        original = getattr(error, "original", error)

        if isinstance(original, MusicBotError):
            embed = Embeds.error(str(original))
        elif isinstance(error, app_commands.CommandOnCooldown):
            embed = Embeds.warning(
                f"Command is on cooldown. Try again in {error.retry_after:.1f}s."
            )
        elif isinstance(error, app_commands.MissingPermissions):
            embed = Embeds.error("You don't have permission to use this command.")
        elif isinstance(error, app_commands.NoPrivateMessage):
            embed = Embeds.error("This command only works on a server.")
        else:
            log.exception("Unhandled command error", exc_info=error)
            embed = Embeds.error(
                "Something went wrong. Try again — and if it keeps happening, let the author know."
            )

        await respond(interaction, embed, ephemeral=True)

    bot.run(settings.token, log_handler=None)


if __name__ == "__main__":
    main()
