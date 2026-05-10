"""Interactive Discord UI components (buttons, selects)."""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any, ClassVar

import discord

from .music_queue import LoopMode
from .source import entry_title, entry_uploader
from .ui import Embeds, Emoji, format_duration

if TYPE_CHECKING:
    from .player import GuildPlayer
    from .track import Track


_LOOP_EMOJI: dict[LoopMode, str] = {
    LoopMode.OFF: Emoji.LOOP_OFF,
    LoopMode.TRACK: Emoji.LOOP_TRACK,
    LoopMode.QUEUE: Emoji.LOOP,
}


def _loop_button_style(mode: LoopMode) -> discord.ButtonStyle:
    return (
        discord.ButtonStyle.success
        if mode is not LoopMode.OFF
        else discord.ButtonStyle.secondary
    )


class NowPlayingView(discord.ui.View):
    """Persistent control panel attached to the now-playing message."""

    def __init__(self, player: GuildPlayer) -> None:
        super().__init__(timeout=None)
        self.player = player
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        self.pause_resume.emoji = (
            Emoji.PLAY if self.player.is_paused else Emoji.PAUSE
        )
        mode = self.player.queue.loop_mode
        self.loop.emoji = _LOOP_EMOJI[mode]
        self.loop.style = _loop_button_style(mode)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message(
                embed=Embeds.error("Buttons are only available on a server."),
                ephemeral=True,
            )
            return False
        if not self.player.is_listener(member):
            await interaction.response.send_message(
                embed=Embeds.error(
                    "Join the same voice channel as the bot to control the player."
                ),
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(emoji=Emoji.PAUSE, style=discord.ButtonStyle.secondary, row=0)
    async def pause_resume(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if self.player.is_paused:
            self.player.resume()
        elif self.player.is_playing:
            self.player.pause()
        else:
            await interaction.response.send_message(
                embed=Embeds.warning("Nothing is playing right now."),
                ephemeral=True,
            )
            return
        self._sync_buttons()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(emoji=Emoji.SKIP, style=discord.ButtonStyle.primary, row=0)
    async def skip(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        member = interaction.user
        assert isinstance(member, discord.Member)
        result = await self.player.vote_skip(member)
        if result.skipped:
            embed = Embeds.success(result.message)
        elif result.error:
            embed = Embeds.error(result.message)
        else:
            embed = Embeds.warning(result.message)
        await interaction.response.send_message(embed=embed, ephemeral=not result.skipped)

    @discord.ui.button(emoji=Emoji.LOOP_OFF, style=discord.ButtonStyle.secondary, row=0)
    async def loop(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        mode = self.player.queue.cycle_loop_mode()
        self._sync_buttons()
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            embed=Embeds.info(f"Loop mode: **{mode.label}**."),
            ephemeral=True,
        )

    @discord.ui.button(emoji=Emoji.QUEUE, style=discord.ButtonStyle.secondary, row=0)
    async def show_queue(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        embed = Embeds.queue(
            self.player.queue.snapshot(),
            self.player.current,
            self.player.queue.loop_mode,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(emoji=Emoji.STOP, style=discord.ButtonStyle.danger, row=0)
    async def stop(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        member = interaction.user
        assert isinstance(member, discord.Member)
        if not self.player.can_control(member):
            await interaction.response.send_message(
                embed=Embeds.error(
                    "Only an admin or the track requester can stop the player."
                ),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=Embeds.info("Stopping playback and leaving the channel.")
        )
        await self.player.stop()


class RemoveTrackView(discord.ui.View):
    """Single-button view for removing the just-added track from the queue."""

    REMOVE_TIMEOUT: ClassVar[float] = 600.0

    def __init__(self, player: GuildPlayer, track: Track) -> None:
        super().__init__(timeout=self.REMOVE_TIMEOUT)
        self.player = player
        self.track = track

    @discord.ui.button(label="Remove", emoji=Emoji.REMOVE, style=discord.ButtonStyle.danger)
    async def remove(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        member = interaction.user
        assert isinstance(member, discord.Member)

        if member.id != self.track.requester.id and not member.guild_permissions.administrator:
            await interaction.response.send_message(
                embed=Embeds.error("You can only remove your own track (or an admin can)."),
                ephemeral=True,
            )
            return

        position = self.player.queue.position_of(self.track)
        if position is None:
            await interaction.response.send_message(
                embed=Embeds.warning("Track is no longer in the queue."),
                ephemeral=True,
            )
            self._disable_all()
            if interaction.message is not None:
                with contextlib.suppress(discord.HTTPException):
                    await interaction.message.edit(view=self)
            return

        self.player.queue.remove_at(position)
        self._disable_all()
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            embed=Embeds.success(f"Track **{self.track.title}** removed from the queue."),
        )

    def _disable_all(self) -> None:
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True


class SearchSelect(discord.ui.Select):
    """Dropdown for choosing among search results."""

    def __init__(
        self,
        entries: list[dict[str, Any]],
        future: asyncio.Future[dict[str, Any]],
    ) -> None:
        options = []
        for index, entry in enumerate(entries):
            title = entry_title(entry)[:100]
            duration = format_duration(entry.get("duration") or 0)
            description = f"{duration} • {entry_uploader(entry)}"[:100]
            options.append(
                discord.SelectOption(label=title, description=description, value=str(index))
            )
        super().__init__(
            placeholder="Pick a track…",
            options=options,
            min_values=1,
            max_values=1,
        )
        self.entries = entries
        self.future = future

    async def callback(self, interaction: discord.Interaction) -> None:
        index = int(self.values[0])
        if not self.future.done():
            self.future.set_result(self.entries[index])
        # Acknowledge the click; the /play handler will edit the original
        # interaction message to show the "added to queue" embed.
        await interaction.response.defer()


class SearchView(discord.ui.View):
    SEARCH_TIMEOUT: ClassVar[float] = 120.0

    def __init__(
        self,
        entries: list[dict[str, Any]],
        future: asyncio.Future[dict[str, Any]],
        *,
        requester_id: int,
        timeout: float | None = None,
    ) -> None:
        super().__init__(timeout=timeout if timeout is not None else self.SEARCH_TIMEOUT)
        self.future = future
        self.requester_id = requester_id
        self.add_item(SearchSelect(entries, future))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                embed=Embeds.error("This is another user's search."),
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        if not self.future.done():
            self.future.cancel()
