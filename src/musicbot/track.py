"""Track domain model."""

from __future__ import annotations

from dataclasses import dataclass

import discord


@dataclass(slots=True)
class Track:
    """A resolved, playable track."""

    stream_url: str
    webpage_url: str
    title: str
    duration: int
    thumbnail: str | None
    uploader: str | None
    requester: discord.Member

    @property
    def is_live(self) -> bool:
        return self.duration <= 0
