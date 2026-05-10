"""Domain-specific exceptions used across the bot."""

from __future__ import annotations


class MusicBotError(Exception):
    """Base error for user-facing music-bot failures."""


class SearchError(MusicBotError):
    """Raised when a search query yields no usable results."""


class SearchTimeoutError(MusicBotError):
    """Raised when the user did not pick a search result in time."""


class ExtractError(MusicBotError):
    """Raised when an audio source cannot be extracted."""


class QueueFullError(MusicBotError):
    """Raised when the queue has reached its maximum size."""
