"""Slash-command surface for the music bot."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, cast

import discord
from discord import app_commands
from discord.ext import commands
from yt_dlp.utils import DownloadError, YoutubeDLError

from .errors import (
    ExtractError,
    QueueFullError,
    SearchError,
    SearchTimeoutError,
)
from .music_queue import LoopMode
from .source import YTDLSource
from .ui import Embeds, respond
from .views import RemoveTrackView, SearchView

if TYPE_CHECKING:
    from .bot import MusicBot
    from .player import GuildPlayer
    from .track import Track


log = logging.getLogger(__name__)

_LOOP_CHOICES = [
    app_commands.Choice(name="Off", value=LoopMode.OFF.value),
    app_commands.Choice(name="Current track", value=LoopMode.TRACK.value),
    app_commands.Choice(name="Queue", value=LoopMode.QUEUE.value),
]


def _user_voice_channel(
    interaction: discord.Interaction,
) -> discord.VoiceChannel | discord.StageChannel | None:
    member = interaction.user
    if not isinstance(member, discord.Member):
        return None
    state = member.voice
    if state is None or state.channel is None:
        return None
    if isinstance(state.channel, (discord.VoiceChannel, discord.StageChannel)):
        return state.channel
    return None


class Music(commands.Cog):
    """Slash commands that talk to the per-guild player."""

    def __init__(self, bot: MusicBot) -> None:
        self.bot = bot

    async def _send_error(
        self, interaction: discord.Interaction, message: str, *, ephemeral: bool = True
    ) -> None:
        await respond(interaction, Embeds.error(message), ephemeral=ephemeral)

    async def _send_warning(
        self, interaction: discord.Interaction, message: str, *, ephemeral: bool = True
    ) -> None:
        await respond(interaction, Embeds.warning(message), ephemeral=ephemeral)

    async def _require_active_player(
        self, interaction: discord.Interaction, *, listener_only: bool = True
    ) -> GuildPlayer | None:
        guild = interaction.guild
        if guild is None:
            await self._send_error(interaction, "This command only works on a server.")
            return None
        player = self.bot.players.get_existing(guild.id)
        if player is None or not player.is_connected:
            await self._send_warning(interaction, "Nothing is playing right now.")
            return None
        member = cast(discord.Member, interaction.user)
        if listener_only and not player.is_admin_or_listener(member):
            await self._send_error(
                interaction,
                "Join the bot's voice channel to control the player.",
            )
            return None
        return player

    @app_commands.command(
        name="play",
        description="Play a track or add it to the queue",
    )
    @app_commands.describe(query="A URL (YouTube etc.) or a search query")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 3.0, key=lambda i: i.user.id)
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        guild = interaction.guild
        if guild is None:
            return

        voice_channel = _user_voice_channel(interaction)
        if voice_channel is None:
            await self._send_error(
                interaction,
                "Join a voice channel to play music.",
            )
            return

        await interaction.response.defer(thinking=True)

        track = await self._fetch_track(interaction, query)
        if track is None:
            return

        player = self.bot.players.get(guild)
        if isinstance(interaction.channel, discord.abc.Messageable):
            player.bind_text_channel(interaction.channel)

        position = await self._enqueue_track(interaction, player, voice_channel, track)
        if position is None:
            return

        player.ensure_loop_running()
        await interaction.edit_original_response(
            embed=Embeds.added(track, position, len(player.queue)),
            view=RemoveTrackView(player, track),
        )

    async def _fetch_track(
        self, interaction: discord.Interaction, query: str
    ) -> Track | None:
        try:
            return await self._resolve_query(interaction, query)
        except SearchTimeoutError as exc:
            embed = Embeds.warning(str(exc))
        except (SearchError, ExtractError) as exc:
            embed = Embeds.error(str(exc))
        except DownloadError as exc:
            log.warning("Track download failed: %s", exc)
            embed = Embeds.error("Failed to download the track.")
        except YoutubeDLError as exc:
            log.warning("yt-dlp error: %s", exc)
            embed = Embeds.error("Failed to process the track.")
        await interaction.edit_original_response(embed=embed, view=None)
        return None

    async def _enqueue_track(
        self,
        interaction: discord.Interaction,
        player: GuildPlayer,
        voice_channel: discord.VoiceChannel | discord.StageChannel,
        track: Track,
    ) -> int | None:
        try:
            await player.connect(voice_channel)
        except discord.Forbidden:
            message = "Failed to connect: missing permissions for the voice channel."
        except TimeoutError:
            message = "Failed to connect: connection timed out."
        except discord.ClientException as exc:
            log.warning("Voice connect failed: %s", exc)
            message = "Failed to connect to the voice channel."
        else:
            message = None

        if message is not None:
            await interaction.edit_original_response(
                embed=Embeds.error(message), view=None
            )
            return None

        try:
            return player.enqueue(track)
        except QueueFullError as exc:
            await interaction.edit_original_response(
                embed=Embeds.error(str(exc)), view=None
            )
            return None

    async def _resolve_query(
        self, interaction: discord.Interaction, query: str
    ) -> Track:
        member = cast(discord.Member, interaction.user)

        if YTDLSource.is_url(query):
            return await YTDLSource.resolve_url(query, member)

        entries = await YTDLSource.search(query, limit=5)
        future: asyncio.Future[dict[str, Any]] = (
            asyncio.get_running_loop().create_future()
        )
        view = SearchView(entries, future, requester_id=member.id)
        await interaction.edit_original_response(
            embed=Embeds.search_results(entries),
            view=view,
        )

        try:
            entry = await asyncio.wait_for(future, timeout=SearchView.SEARCH_TIMEOUT)
        except (TimeoutError, asyncio.CancelledError) as exc:
            view.stop()
            raise SearchTimeoutError("Selection timed out.") from exc

        return await YTDLSource.resolve_entry(entry, member)

    @app_commands.command(name="skip", description="Skip the current track")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 2.0, key=lambda i: i.user.id)
    async def skip(self, interaction: discord.Interaction) -> None:
        player = await self._require_active_player(interaction, listener_only=False)
        if player is None:
            return
        member = cast(discord.Member, interaction.user)
        result = await player.vote_skip(member)
        if result.skipped:
            await interaction.response.send_message(embed=Embeds.success(result.message))
        elif result.error:
            await interaction.response.send_message(
                embed=Embeds.error(result.message), ephemeral=True
            )
        else:
            await interaction.response.send_message(embed=Embeds.info(result.message))

    @app_commands.command(name="pause", description="Pause playback")
    @app_commands.guild_only()
    async def pause(self, interaction: discord.Interaction) -> None:
        player = await self._require_active_player(interaction)
        if player is None:
            return
        if player.pause():
            await interaction.response.send_message(
                embed=Embeds.success("Playback paused.")
            )
        else:
            await self._send_warning(interaction, "Nothing to pause.")

    @app_commands.command(name="resume", description="Resume playback from pause")
    @app_commands.guild_only()
    async def resume(self, interaction: discord.Interaction) -> None:
        player = await self._require_active_player(interaction)
        if player is None:
            return
        if player.resume():
            await interaction.response.send_message(
                embed=Embeds.success("Playback resumed.")
            )
        else:
            await self._send_warning(interaction, "Playback is already running.")

    @app_commands.command(
        name="stop",
        description="Stop playback and leave the channel",
    )
    @app_commands.guild_only()
    async def stop(self, interaction: discord.Interaction) -> None:
        player = await self._require_active_player(interaction)
        if player is None:
            return
        await interaction.response.send_message(
            embed=Embeds.info("Stopping playback and leaving the channel.")
        )
        await player.stop()

    @app_commands.command(name="queue", description="Show the current queue")
    @app_commands.guild_only()
    async def queue(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return
        player = self.bot.players.get_existing(guild.id)
        if player is None or (not player.queue and player.current is None):
            await interaction.response.send_message(
                embed=Embeds.info("The queue is empty."), ephemeral=True
            )
            return
        embed = Embeds.queue(
            player.queue.snapshot(),
            player.current,
            player.queue.loop_mode,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="clear", description="Clear the queue")
    @app_commands.guild_only()
    async def clear(self, interaction: discord.Interaction) -> None:
        player = await self._require_active_player(interaction)
        if player is None:
            return
        removed = player.queue.clear()
        if removed:
            await interaction.response.send_message(
                embed=Embeds.success(f"Queue cleared ({removed} tracks).")
            )
        else:
            await self._send_warning(interaction, "The queue is already empty.")

    @app_commands.command(
        name="remove",
        description="Remove a track from the queue by position",
    )
    @app_commands.describe(position="Track number in the queue (1, 2, 3...)")
    @app_commands.guild_only()
    async def remove(
        self,
        interaction: discord.Interaction,
        position: app_commands.Range[int, 1, 500],
    ) -> None:
        player = await self._require_active_player(interaction)
        if player is None:
            return

        try:
            target = player.queue.peek(position)
        except IndexError:
            await self._send_error(
                interaction,
                f"Position {position} is out of range (1..{len(player.queue)}).",
            )
            return

        member = cast(discord.Member, interaction.user)
        if (
            target.requester.id != member.id
            and not member.guild_permissions.administrator
        ):
            await self._send_error(
                interaction,
                "Only the requester or an admin can remove someone else's track.",
            )
            return

        track = player.queue.remove_at(position)
        await interaction.response.send_message(
            embed=Embeds.success(f"Track **{track.title}** removed from the queue.")
        )

    @app_commands.command(name="shuffle", description="Shuffle the queue")
    @app_commands.guild_only()
    async def shuffle(self, interaction: discord.Interaction) -> None:
        player = await self._require_active_player(interaction)
        if player is None:
            return
        if len(player.queue) < 2:
            await self._send_warning(
                interaction, "The queue must contain at least 2 tracks."
            )
            return
        player.queue.shuffle()
        await interaction.response.send_message(
            embed=Embeds.success("Queue shuffled.")
        )

    @app_commands.command(name="loop", description="Control loop mode")
    @app_commands.describe(mode="Loop mode (without an argument it cycles through modes)")
    @app_commands.choices(mode=_LOOP_CHOICES)
    @app_commands.guild_only()
    async def loop(
        self,
        interaction: discord.Interaction,
        mode: app_commands.Choice[str] | None = None,
    ) -> None:
        player = await self._require_active_player(interaction)
        if player is None:
            return
        if mode is None:
            new_mode = player.queue.cycle_loop_mode()
        else:
            new_mode = LoopMode(mode.value)
            player.queue.set_loop_mode(new_mode)
        await interaction.response.send_message(
            embed=Embeds.success(f"Loop mode: **{new_mode.label}**.")
        )

    @app_commands.command(
        name="nowplaying",
        description="Show the current track with progress",
    )
    @app_commands.guild_only()
    async def nowplaying(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return
        player = self.bot.players.get_existing(guild.id)
        if player is None or player.current is None:
            await interaction.response.send_message(
                embed=Embeds.info("Nothing is playing right now."), ephemeral=True
            )
            return

        embed = Embeds.progress(player.current, player.elapsed, player.queue.loop_mode)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="volume",
        description="Set playback volume (0–200%)",
    )
    @app_commands.describe(level="Volume as a percentage (default is 100)")
    @app_commands.guild_only()
    async def volume(
        self,
        interaction: discord.Interaction,
        level: app_commands.Range[int, 0, 200],
    ) -> None:
        player = await self._require_active_player(interaction)
        if player is None:
            return
        applied = player.set_volume(level / 100.0)
        await interaction.response.send_message(
            embed=Embeds.success(f"Volume: **{int(applied * 100)}%**.")
        )

    @app_commands.command(name="help", description="List of available commands")
    async def help_cmd(self, interaction: discord.Interaction) -> None:
        commands_data = [
            (cmd.name, cmd.description or "—")
            for cmd in self.bot.tree.get_commands()
            if isinstance(cmd, app_commands.Command)
        ]
        commands_data.sort(key=lambda x: x[0])
        await interaction.response.send_message(
            embed=Embeds.help_(commands_data), ephemeral=True
        )

    @app_commands.command(name="about", description="About the bot and author")
    async def about(self, interaction: discord.Interaction) -> None:
        assert self.bot.user is not None
        embed = Embeds.about(self.bot.user, len(self.bot.guilds))
        await interaction.response.send_message(embed=embed, ephemeral=True)
