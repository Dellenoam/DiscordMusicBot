"""Audio source resolution via yt-dlp."""

from __future__ import annotations

import asyncio
import logging
import re
import threading
from typing import IO, TYPE_CHECKING, Any, ClassVar, cast

import discord
import yt_dlp

from .errors import ExtractError, SearchError
from .track import Track

if TYPE_CHECKING:
    from .config import Settings


_UNKNOWN = "Unknown"
_thread_local = threading.local()
_yt_dlp_log = logging.getLogger("yt_dlp")
_ffmpeg_log = logging.getLogger("ffmpeg")


class _YDLLogger:
    """Routes yt-dlp's stderr output through Python logging.

    yt-dlp calls ``report_error`` even when ``ignoreerrors=True`` — those errors
    are recovered from internally and only useful for debugging, so we demote
    them to DEBUG. Real failures still surface as ``DownloadError`` exceptions
    that we handle and log at the call site.
    """

    def debug(self, msg: str) -> None:
        _yt_dlp_log.debug(msg)

    def info(self, msg: str) -> None:
        _yt_dlp_log.debug(msg)

    def warning(self, msg: str) -> None:
        _yt_dlp_log.warning(msg)

    def error(self, msg: str) -> None:
        _yt_dlp_log.debug(msg)


_YDL_LOGGER = _YDLLogger()


class _FFmpegStderrSink:
    """File-like sink that routes ffmpeg's stderr through Python logging.

    Without this, ffmpeg inherits the parent process's stderr and noisy
    non-fatal lines (e.g. ``[opus @ ...] Error parsing Opus packet header``
    when a stream packet is malformed but recovery succeeds) get mixed into
    our logs. We omit ``fileno()`` on purpose so discord.py picks the
    pipe-reader thread path and feeds bytes to ``write()``.
    """

    def __init__(self) -> None:
        self._buffer = bytearray()

    def write(self, data: bytes) -> int:
        self._buffer.extend(data)
        while True:
            idx = self._buffer.find(b"\n")
            if idx < 0:
                break
            line = bytes(self._buffer[:idx])
            del self._buffer[: idx + 1]
            text = line.decode(errors="ignore").rstrip()
            if text:
                _ffmpeg_log.debug(text)
        return len(data)

    def close(self) -> None:
        if self._buffer:
            text = bytes(self._buffer).decode(errors="ignore").rstrip()
            if text:
                _ffmpeg_log.debug(text)
            self._buffer.clear()


def entry_title(entry: dict[str, Any]) -> str:
    return entry.get("title") or _UNKNOWN


def entry_uploader(entry: dict[str, Any]) -> str:
    return entry.get("uploader") or entry.get("channel") or _UNKNOWN


class YTDLSource:
    """Resolves search queries and URLs into playable :class:`Track` objects."""

    YTDL_OPTIONS: ClassVar[dict[str, Any]] = {
        "format": "bestaudio[acodec=opus]/bestaudio/best",
        "quiet": True,
        "no_warnings": True,
        "no_color": True,
        "default_search": "ytsearch",
        "noplaylist": True,
        "ignoreerrors": False,
        "logtostderr": False,
        "skip_download": True,
        "extract_flat": False,
        "logger": _YDL_LOGGER,
    }

    _options_generation: ClassVar[int] = 0

    FFMPEG_BEFORE_OPTIONS: ClassVar[str] = (
        "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin"
    )
    FFMPEG_OPTIONS: ClassVar[str] = "-vn -loglevel warning"

    _URL_RE: ClassVar[re.Pattern[str]] = re.compile(r"^https?://", re.IGNORECASE)

    @classmethod
    def configure(cls, settings: Settings) -> None:
        """Apply runtime settings; call once at startup before any extract."""
        if settings.ydl_force_ipv4:
            cls.YTDL_OPTIONS["source_address"] = "0.0.0.0"
        else:
            cls.YTDL_OPTIONS.pop("source_address", None)
        cls._options_generation += 1

    @classmethod
    def is_url(cls, query: str) -> bool:
        return bool(cls._URL_RE.match(query.strip()))

    @classmethod
    def _get_ydl(cls, *, lenient: bool = False) -> yt_dlp.YoutubeDL:
        attr = "ydl_lenient" if lenient else "ydl_strict"
        gen_attr = f"{attr}_gen"
        cached = getattr(_thread_local, attr, None)
        cached_gen = getattr(_thread_local, gen_attr, -1)
        if cached is None or cached_gen != cls._options_generation:
            opts = dict(cls.YTDL_OPTIONS)
            if lenient:
                opts["ignoreerrors"] = True
            cached = yt_dlp.YoutubeDL(cast("Any", opts))
            setattr(_thread_local, attr, cached)
            setattr(_thread_local, gen_attr, cls._options_generation)
        return cached

    @classmethod
    def _extract(cls, target: str, *, lenient: bool = False) -> dict[str, Any] | None:
        info = cls._get_ydl(lenient=lenient).extract_info(target, download=False)
        return cast("dict[str, Any] | None", info)

    @classmethod
    async def search(cls, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        """Search for tracks; returns up to ``limit`` usable entries.

        Skips unavailable videos so a single bad result doesn't kill the search.
        """
        info = await asyncio.to_thread(
            cls._extract, f"ytsearch{limit}:{query}", lenient=True
        )
        if info is None:
            raise SearchError(f"No results found for `{query}`.")
        entries = cast(
            list[dict[str, Any]], [e for e in (info.get("entries") or []) if e]
        )
        if not entries:
            raise SearchError(f"No results found for `{query}`.")
        return entries

    @classmethod
    async def resolve_url(cls, url: str, requester: discord.Member) -> Track:
        info = await asyncio.to_thread(cls._extract, url)
        if info is None:
            raise ExtractError("Failed to retrieve track information.")
        if info.get("_type") == "playlist":
            entries = [e for e in (info.get("entries") or []) if e]
            if not entries:
                raise ExtractError("Playlist is empty or contains only private tracks.")
            info = entries[0]
        return cls._build_track(cast(dict[str, Any], info), requester)

    @classmethod
    async def resolve_entry(
        cls, entry: dict[str, Any], requester: discord.Member
    ) -> Track:
        """Resolve a (possibly flat) search entry to a fully populated Track."""
        if entry.get("url") and entry.get("_type") not in ("url", "url_transparent"):
            return cls._build_track(entry, requester)
        page_url = entry.get("webpage_url") or entry.get("url")
        if not page_url:
            raise ExtractError("Failed to determine the track URL.")
        return await cls.resolve_url(page_url, requester)

    @classmethod
    def make_audio_source(
        cls, track: Track, *, volume: float = 1.0
    ) -> discord.AudioSource:
        return discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(
                track.stream_url,
                before_options=cls.FFMPEG_BEFORE_OPTIONS,
                options=cls.FFMPEG_OPTIONS,
                stderr=cast("IO[bytes]", _FFmpegStderrSink()),
            ),
            volume=volume,
        )

    @staticmethod
    def _build_track(info: dict[str, Any], requester: discord.Member) -> Track:
        stream_url = info.get("url")
        if not stream_url:
            raise ExtractError("Source did not return a direct audio URL.")
        return Track(
            stream_url=stream_url,
            webpage_url=info.get("webpage_url") or info.get("original_url") or "",
            title=entry_title(info),
            duration=int(info.get("duration") or 0),
            thumbnail=info.get("thumbnail"),
            uploader=info.get("uploader") or info.get("channel"),
            requester=requester,
        )
