from dataclasses import dataclass
import discord


@dataclass
class TrackInfo:
    url: str
    title: str
    author: discord.abc.User
