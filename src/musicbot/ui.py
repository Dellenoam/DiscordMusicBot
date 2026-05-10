"""Visual building blocks: theme, emojis, embed factories, formatters."""

from __future__ import annotations

import discord

from .music_queue import LoopMode
from .source import entry_title, entry_uploader
from .track import Track

FOOTER_TEXT = "Made by Dellenoam"
FOOTER_EMOJI = "❤️"


class Theme:
    PRIMARY = 0xA78BFA  # lavender
    SUCCESS = 0x10B981  # emerald
    DANGER = 0xEF4444  # red
    WARNING = 0xF59E0B  # amber
    INFO = 0x60A5FA  # sky
    PLAYING = 0x8B5CF6  # violet
    QUEUED = 0x6366F1  # indigo


class Emoji:
    PLAY = "▶️"
    PAUSE = "⏸️"
    SKIP = "⏭️"
    STOP = "⏹️"
    LOOP = "🔁"
    LOOP_TRACK = "🔂"
    LOOP_OFF = "➡️"
    SHUFFLE = "🔀"
    QUEUE = "📋"
    MUSIC = "🎵"
    DISC = "💿"
    HEART = "❤️"
    USER = "👤"
    LIVE = "🔴"
    CLEAR = "🧹"
    REMOVE = "✖️"
    LINK = "🔗"
    INFO = "ℹ️"
    WARN = "⚠️"
    OK = "✅"
    ERROR = "🚫"
    VOLUME = "🔊"
    HOURGLASS = "⏳"


def format_duration(seconds: float | None) -> str:
    if not seconds or seconds <= 0:
        return f"{Emoji.LIVE} LIVE"
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def progress_bar(current: float, total: float, *, length: int = 20) -> str:
    if total <= 0:
        return "▱" * length
    ratio = max(0.0, min(1.0, current / total))
    filled = int(ratio * length)
    return "▰" * filled + "▱" * (length - filled)


def loop_indicator(mode: LoopMode) -> str:
    return {
        LoopMode.OFF: "",
        LoopMode.TRACK: f" {Emoji.LOOP_TRACK}",
        LoopMode.QUEUE: f" {Emoji.LOOP}",
    }[mode]


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _apply_footer(embed: discord.Embed, suffix: str | None = None) -> discord.Embed:
    base = f"{FOOTER_TEXT} {FOOTER_EMOJI}"
    embed.set_footer(text=f"{suffix} • {base}" if suffix else base)
    return embed


async def respond(
    interaction: discord.Interaction,
    embed: discord.Embed,
    *,
    ephemeral: bool = True,
) -> None:
    """Send an embed reply via the right channel (response vs followup)."""
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
    except discord.HTTPException:
        pass


class Embeds:
    """Factory of styled :class:`discord.Embed` instances."""

    @staticmethod
    def now_playing(track: Track, loop_mode: LoopMode = LoopMode.OFF) -> discord.Embed:
        embed = discord.Embed(
            title=f"{Emoji.DISC} Now playing{loop_indicator(loop_mode)}",
            description=f"### [{_truncate(track.title, 100)}]({track.webpage_url})",
            color=Theme.PLAYING,
        )
        if track.uploader:
            embed.add_field(
                name=f"{Emoji.USER} Channel",
                value=_truncate(track.uploader, 100),
                inline=True,
            )
        embed.add_field(
            name=f"{Emoji.HOURGLASS} Duration",
            value=format_duration(track.duration),
            inline=True,
        )
        embed.add_field(
            name=f"{Emoji.MUSIC} Requested by",
            value=track.requester.mention,
            inline=True,
        )
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
        return _apply_footer(embed)

    @staticmethod
    def added(track: Track, position: int, queue_size: int) -> discord.Embed:
        embed = discord.Embed(
            title=f"{Emoji.OK} Added to queue",
            description=f"### [{_truncate(track.title, 100)}]({track.webpage_url})",
            color=Theme.SUCCESS,
        )
        embed.add_field(name="Position", value=f"`#{position}`", inline=True)
        embed.add_field(
            name=f"{Emoji.HOURGLASS} Duration",
            value=format_duration(track.duration),
            inline=True,
        )
        embed.add_field(
            name=f"{Emoji.MUSIC} Requested by",
            value=track.requester.mention,
            inline=True,
        )
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
        suffix = f"In queue: {queue_size}" if queue_size else None
        return _apply_footer(embed, suffix)

    @staticmethod
    def queue(
        tracks: list[Track],
        current: Track | None,
        loop_mode: LoopMode,
        *,
        limit: int = 15,
    ) -> discord.Embed:
        embed = discord.Embed(
            title=f"{Emoji.QUEUE} Playback queue",
            color=Theme.QUEUED,
        )

        if current is not None:
            embed.description = (
                f"**{Emoji.PLAY} Now playing**\n"
                f"[{_truncate(current.title, 80)}]({current.webpage_url})"
                f" • `{format_duration(current.duration)}`"
                f" • {current.requester.mention}"
            )

        if tracks:
            lines: list[str] = []
            for index, track in enumerate(tracks[:limit], start=1):
                lines.append(
                    f"`{index:>2}.` **[{_truncate(track.title, 60)}]"
                    f"({track.webpage_url})** • "
                    f"`{format_duration(track.duration)}` • "
                    f"{track.requester.mention}"
                )
            if len(tracks) > limit:
                lines.append(f"*…and **{len(tracks) - limit}** more tracks*")

            field_value = "\n".join(lines)
            embed.add_field(
                name=f"{Emoji.MUSIC} Up next ({len(tracks)})",
                value=field_value,
                inline=False,
            )
        elif current is None:
            embed.description = "*The queue is empty.*"
        else:
            embed.add_field(
                name=f"{Emoji.MUSIC} Up next",
                value="*The queue is empty.*",
                inline=False,
            )

        total = sum(t.duration for t in tracks if t.duration > 0)
        meta_parts = []
        if total:
            meta_parts.append(f"Total time: {format_duration(total)}")
        if loop_mode is not LoopMode.OFF:
            meta_parts.append(f"Loop: {loop_mode.label}")
        suffix = " • ".join(meta_parts) if meta_parts else None
        return _apply_footer(embed, suffix)

    @staticmethod
    def search_results(entries: list[dict]) -> discord.Embed:
        lines: list[str] = []
        for index, entry in enumerate(entries, start=1):
            title = _truncate(entry_title(entry), 70)
            duration = format_duration(entry.get("duration") or 0)
            uploader = _truncate(entry_uploader(entry), 40)
            lines.append(
                f"`{index}.` **{title}**\n"
                f"      {Emoji.USER} {uploader} • `{duration}`"
            )
        embed = discord.Embed(
            title=f"{Emoji.MUSIC} Search results",
            description="\n".join(lines),
            color=Theme.INFO,
        )
        return _apply_footer(embed, "Pick a track below")

    @staticmethod
    def progress(track: Track, elapsed: float, loop_mode: LoopMode) -> discord.Embed:
        bar = progress_bar(elapsed, track.duration)
        embed = discord.Embed(
            title=f"{Emoji.DISC} Now playing{loop_indicator(loop_mode)}",
            description=(
                f"### [{_truncate(track.title, 100)}]({track.webpage_url})\n\n"
                f"`{bar}`\n"
                f"`{format_duration(elapsed)} / {format_duration(track.duration)}`"
            ),
            color=Theme.PLAYING,
        )
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
        embed.add_field(
            name=f"{Emoji.USER} Channel",
            value=_truncate(track.uploader or "—", 100),
            inline=True,
        )
        embed.add_field(
            name=f"{Emoji.MUSIC} Requested by",
            value=track.requester.mention,
            inline=True,
        )
        return _apply_footer(embed)

    @staticmethod
    def about(bot_user: discord.ClientUser, guild_count: int) -> discord.Embed:
        embed = discord.Embed(
            title=f"{Emoji.MUSIC} About",
            description=(
                "A modern music bot for Discord.\n"
                "Plays music from YouTube and other sources via `yt-dlp`.\n\n"
                f"**Made with {Emoji.HEART} by [Dellenoam]"
                "(https://github.com/Dellenoam)**"
            ),
            color=Theme.PLAYING,
        )
        if bot_user.display_avatar:
            embed.set_thumbnail(url=bot_user.display_avatar.url)
        embed.add_field(name="Servers", value=f"`{guild_count}`", inline=True)
        embed.add_field(name="Commands", value="`/help`", inline=True)
        embed.add_field(
            name="Source",
            value="[GitHub](https://github.com/Dellenoam/DiscordMusicBot)",
            inline=True,
        )
        return _apply_footer(embed)

    @staticmethod
    def help_(commands_data: list[tuple[str, str]]) -> discord.Embed:
        lines = [f"**`/{name}`** — {desc}" for name, desc in commands_data]
        embed = discord.Embed(
            title=f"{Emoji.INFO} Available commands",
            description="\n".join(lines),
            color=Theme.INFO,
        )
        return _apply_footer(embed)

    @staticmethod
    def info(message: str) -> discord.Embed:
        return _apply_footer(
            discord.Embed(
                description=f"{Emoji.INFO}  {message}",
                color=Theme.INFO,
            )
        )

    @staticmethod
    def success(message: str) -> discord.Embed:
        return _apply_footer(
            discord.Embed(
                description=f"{Emoji.OK}  {message}",
                color=Theme.SUCCESS,
            )
        )

    @staticmethod
    def warning(message: str) -> discord.Embed:
        return _apply_footer(
            discord.Embed(
                description=f"{Emoji.WARN}  {message}",
                color=Theme.WARNING,
            )
        )

    @staticmethod
    def error(message: str) -> discord.Embed:
        return _apply_footer(
            discord.Embed(
                description=f"{Emoji.ERROR}  {message}",
                color=Theme.DANGER,
            )
        )
