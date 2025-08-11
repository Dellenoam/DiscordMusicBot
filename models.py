from dataclasses import dataclass
from typing import Optional

import discord


@dataclass
class TrackInfo:
    url: str
    title: str
    author: discord.abc.User
    duration: int
    thumbnail: Optional[str] = None
