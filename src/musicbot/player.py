"""Per-guild music player and player manager."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import discord

from .errors import QueueFullError
from .music_queue import LoopMode, MusicQueue
from .source import YTDLSource
from .track import Track
from .ui import Embeds
from .views import NowPlayingView

if TYPE_CHECKING:
    from .bot import MusicBot
    from .config import Settings


log = logging.getLogger(__name__)


@dataclass(slots=True)
class SkipResult:
    skipped: bool
    message: str
    error: bool = False


class GuildPlayer:
    """Owns voice state, queue and playback loop for a single guild."""

    MAX_CONSECUTIVE_FAILURES: ClassVar[int] = 3
    DISCONNECT_TIMEOUT: ClassVar[float] = 5.0
    SHUTDOWN_TIMEOUT: ClassVar[float] = 10.0

    def __init__(self, bot: MusicBot, guild: discord.Guild) -> None:
        self.bot = bot
        self.guild = guild
        self.queue = MusicQueue()
        self.current: Track | None = None
        self.current_started_at: float | None = None
        self.text_channel: discord.abc.Messageable | None = None
        self.now_playing_msg: discord.Message | None = None
        self.skip_votes: set[int] = set()
        self.volume: float = 1.0

        self._next_event = asyncio.Event()
        self._queue_added = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._closing = False
        self._track_errored = False
        self._consecutive_failures = 0
        self._empty_disconnect_task: asyncio.Task[None] | None = None

    @property
    def elapsed(self) -> float:
        if self.current_started_at is None:
            return 0.0
        return max(0.0, time.monotonic() - self.current_started_at)

    @property
    def voice_client(self) -> discord.VoiceClient | None:
        vc = self.guild.voice_client
        if isinstance(vc, discord.VoiceClient):
            return vc
        return None

    @property
    def is_connected(self) -> bool:
        vc = self.voice_client
        return bool(vc and vc.is_connected())

    @property
    def is_playing(self) -> bool:
        vc = self.voice_client
        return bool(vc and vc.is_playing())

    @property
    def is_paused(self) -> bool:
        vc = self.voice_client
        return bool(vc and vc.is_paused())

    def is_listener(self, member: discord.Member) -> bool:
        """True if ``member`` is in the same voice channel as the bot."""
        vc = self.voice_client
        return bool(
            vc
            and member.voice
            and member.voice.channel
            and member.voice.channel.id == vc.channel.id
        )

    def is_admin_or_listener(self, member: discord.Member) -> bool:
        return member.guild_permissions.administrator or self.is_listener(member)

    def can_control(self, member: discord.Member) -> bool:
        """Admin OR requester of the currently playing track."""
        if member.guild_permissions.administrator:
            return True
        return self.current is not None and self.current.requester.id == member.id

    def human_listeners(self) -> list[discord.Member]:
        vc = self.voice_client
        if vc is None:
            return []
        return [m for m in vc.channel.members if not m.bot]

    def bind_text_channel(self, channel: discord.abc.Messageable) -> None:
        self.text_channel = channel

    async def connect(
        self, channel: discord.VoiceChannel | discord.StageChannel
    ) -> None:
        vc = self.voice_client
        if vc and vc.is_connected():
            if vc.channel.id != channel.id:
                await vc.move_to(channel)
            return
        await channel.connect(self_deaf=True)

    def enqueue(self, track: Track) -> int:
        """Add a track to the queue and wake the playback loop if idle."""
        position = self.queue.add(track)
        self._queue_added.set()
        return position

    def ensure_loop_running(self) -> None:
        if self._task is None or self._task.done():
            self._task = self.bot.loop.create_task(
                self._playback_loop(),
                name=f"music-loop:{self.guild.id}",
            )

    def schedule_disconnect_if_empty(self) -> None:
        """Disconnect after a grace period if the channel stays empty."""
        if self._closing:
            return
        grace = self.bot.settings.empty_channel_grace
        if grace <= 0:
            self.bot.loop.create_task(self.stop(), name=f"empty-stop:{self.guild.id}")
            return
        if self._empty_disconnect_task and not self._empty_disconnect_task.done():
            return
        self._empty_disconnect_task = self.bot.loop.create_task(
            self._disconnect_after_grace(grace),
            name=f"empty-disconnect:{self.guild.id}",
        )

    def cancel_disconnect_grace(self) -> None:
        task = self._empty_disconnect_task
        if task and not task.done():
            task.cancel()
        self._empty_disconnect_task = None

    async def _disconnect_after_grace(self, grace: int) -> None:
        try:
            await asyncio.sleep(grace)
        except asyncio.CancelledError:
            return
        if self._closing or self.human_listeners():
            return
        log.info("Voice channel empty after grace, leaving guild %s", self.guild.id)
        await self.stop()

    async def _playback_loop(self) -> None:
        try:
            while not self._closing:
                track = await self._next_track()
                if track is None:
                    if not self._closing:
                        await self._send(Embeds.info("Queue is empty, disconnecting."))
                    return
                await self._play_one(track)
        except Exception:
            log.exception("Playback loop crashed for guild %s", self.guild.id)
        finally:
            await self._teardown()

    async def _next_track(self) -> Track | None:
        if self.current is not None:
            previous = self.current
            errored = self._track_errored
            self._track_errored = False
            self.current = None

            if errored:
                self._consecutive_failures += 1
                if self._consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                    await self._send(
                        Embeds.error(
                            "Too many consecutive errors, stopping playback."
                        )
                    )
                    return None
            else:
                self._consecutive_failures = 0
                if self.queue.loop_mode is LoopMode.TRACK:
                    self.current = previous
                    return previous
                if self.queue.loop_mode is LoopMode.QUEUE:
                    try:
                        self.queue.add(previous)
                    except QueueFullError as exc:
                        await self._send(Embeds.warning(str(exc)))

        if self.queue:
            return self.queue.pop_next()

        timeout = self.bot.settings.inactivity_timeout
        try:
            await asyncio.wait_for(self._wait_for_track(), timeout=timeout)
        except TimeoutError:
            return None
        if self._closing:
            return None
        return self.queue.pop_next()

    async def _wait_for_track(self) -> None:
        # Event-driven wait: cleared before each check to avoid a race where
        # a set() between the queue check and wait() would otherwise be lost.
        while not self.queue and not self._closing:
            self._queue_added.clear()
            if self.queue or self._closing:
                return
            await self._queue_added.wait()

    async def _play_one(self, track: Track) -> None:
        self.current = track
        self.skip_votes.clear()
        self._next_event.clear()
        self._track_errored = False

        vc = self.voice_client
        if vc is None or not vc.is_connected():
            log.warning("Voice client gone before playback for guild %s", self.guild.id)
            self._track_errored = True
            await self._send(
                Embeds.error(
                    f"Failed to play **{track.title}**: "
                    "the bot is not in a voice channel."
                )
            )
            return

        try:
            source = YTDLSource.make_audio_source(track, volume=self.volume)
        except Exception:
            log.exception("Failed to build audio source for %s", track.title)
            self._track_errored = True
            await self._send(Embeds.error(f"Failed to play **{track.title}**."))
            return

        try:
            vc.play(source, after=self._after_play)
        except discord.ClientException:
            log.exception("voice_client.play failed for guild %s", self.guild.id)
            self._track_errored = True
            await self._send(Embeds.error(f"Failed to start **{track.title}**."))
            return

        self.current_started_at = time.monotonic()
        await self._send_now_playing(track)

        try:
            await self._next_event.wait()
        finally:
            await self._cleanup_now_playing_view()

    def _after_play(self, error: Exception | None) -> None:
        if error:
            log.error("Playback finished with error: %s", error, exc_info=error)
            self._track_errored = True
        with contextlib.suppress(RuntimeError):
            self.bot.loop.call_soon_threadsafe(self._next_event.set)

    async def _send_now_playing(self, track: Track) -> None:
        if self.text_channel is None:
            return
        embed = Embeds.now_playing(track, self.queue.loop_mode)
        view = NowPlayingView(self)
        try:
            self.now_playing_msg = await self.text_channel.send(embed=embed, view=view)
        except discord.HTTPException:
            log.warning("Failed to send now-playing message", exc_info=True)
            self.now_playing_msg = None

    async def _cleanup_now_playing_view(self) -> None:
        if self.now_playing_msg is None:
            return
        with contextlib.suppress(discord.HTTPException):
            await self.now_playing_msg.edit(view=None)
        self.now_playing_msg = None

    async def _send(self, embed: discord.Embed) -> None:
        if self.text_channel is None:
            return
        with contextlib.suppress(discord.HTTPException):
            await self.text_channel.send(embed=embed)

    def pause(self) -> bool:
        vc = self.voice_client
        if vc and vc.is_playing():
            vc.pause()
            return True
        return False

    def resume(self) -> bool:
        vc = self.voice_client
        if vc and vc.is_paused():
            vc.resume()
            return True
        return False

    async def skip(self) -> None:
        vc = self.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()

    def set_volume(self, value: float) -> float:
        clamped = max(0.0, min(2.0, value))
        if clamped == self.volume:
            return clamped
        self.volume = clamped
        vc = self.voice_client
        source = vc.source if vc else None
        if isinstance(source, discord.PCMVolumeTransformer):
            source.volume = self.volume
        return self.volume

    async def stop(self) -> None:
        """Clear queue, stop playback and disconnect from voice."""
        if self._closing:
            return
        self._closing = True
        self.cancel_disconnect_grace()
        self.queue.clear()
        self._queue_added.set()
        self._next_event.set()
        vc = self.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
        task = self._task
        if task is None or task.done():
            await self._teardown()
            return
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=self.SHUTDOWN_TIMEOUT)
        except TimeoutError:
            log.warning(
                "Playback task did not exit gracefully in guild %s, cancelling",
                self.guild.id,
            )
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def vote_skip(self, member: discord.Member) -> SkipResult:
        """Apply skip rules and return the user-facing result."""
        settings = self.bot.settings
        vc = self.voice_client
        if vc is None or not (vc.is_playing() or vc.is_paused()):
            return SkipResult(skipped=False, message="Nothing is playing right now.", error=True)

        if not self.is_listener(member):
            return SkipResult(
                skipped=False,
                message="Join the bot's voice channel.",
                error=True,
            )

        instant_message = self._instant_skip_message(member, settings)
        if instant_message is not None:
            await self.skip()
            return SkipResult(skipped=True, message=instant_message)

        listeners = self.human_listeners()
        total = max(1, len(listeners))
        needed = max(1, math.ceil(total * settings.skip_vote_ratio))

        if member.id in self.skip_votes:
            return SkipResult(
                skipped=False,
                message=f"You already voted. Votes: **{len(self.skip_votes)}/{needed}**.",
                error=True,
            )

        self.skip_votes.add(member.id)

        if len(self.skip_votes) >= needed:
            await self.skip()
            return SkipResult(
                skipped=True,
                message=f"Track skipped **{len(self.skip_votes)}/{total}**.",
            )

        return SkipResult(
            skipped=False,
            message=f"Vote accepted: **{len(self.skip_votes)}/{needed}**.",
        )

    def _instant_skip_message(
        self, member: discord.Member, settings: Settings
    ) -> str | None:
        if settings.admin_instant_skip and member.guild_permissions.administrator:
            return "Track skipped by an administrator."
        if (
            settings.requester_instant_skip
            and self.current
            and self.current.requester.id == member.id
        ):
            return "Track skipped by the requester."
        return None

    async def _teardown(self) -> None:
        await self._cleanup_now_playing_view()
        vc = self.voice_client
        if vc and vc.is_connected():
            try:
                await asyncio.wait_for(
                    vc.disconnect(force=False), timeout=self.DISCONNECT_TIMEOUT
                )
            except (TimeoutError, discord.HTTPException):
                log.warning(
                    "Graceful disconnect failed in guild %s, forcing", self.guild.id
                )
                with contextlib.suppress(Exception):
                    await vc.disconnect(force=True)
        self.current = None
        self.current_started_at = None
        self.bot.players.remove(self.guild.id)


class PlayerManager:
    """Owns all :class:`GuildPlayer` instances for the running bot."""

    def __init__(self, bot: MusicBot) -> None:
        self.bot = bot
        self._players: dict[int, GuildPlayer] = {}

    def get(self, guild: discord.Guild) -> GuildPlayer:
        player = self._players.get(guild.id)
        if player is None:
            player = GuildPlayer(self.bot, guild)
            self._players[guild.id] = player
        return player

    def get_existing(self, guild_id: int) -> GuildPlayer | None:
        return self._players.get(guild_id)

    def remove(self, guild_id: int) -> None:
        self._players.pop(guild_id, None)

    async def shutdown(self) -> None:
        results = await asyncio.gather(
            *(player.stop() for player in list(self._players.values())),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                log.exception("Error stopping player", exc_info=result)
        self._players.clear()
