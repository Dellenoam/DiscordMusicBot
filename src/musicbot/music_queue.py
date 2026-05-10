"""Per-guild track queue with loop modes."""

from __future__ import annotations

import enum
import random
from collections import deque
from collections.abc import Iterator
from typing import ClassVar

from .errors import QueueFullError
from .track import Track


class LoopMode(enum.Enum):
    OFF = "off"
    TRACK = "track"
    QUEUE = "queue"

    @property
    def label(self) -> str:
        return {
            LoopMode.OFF: "Off",
            LoopMode.TRACK: "Current track",
            LoopMode.QUEUE: "Queue",
        }[self]


class MusicQueue:
    """A simple FIFO queue with helpers for management and looping."""

    DEFAULT_MAX_SIZE = 500
    _CYCLE_ORDER: ClassVar[tuple[LoopMode, ...]] = (
        LoopMode.OFF,
        LoopMode.TRACK,
        LoopMode.QUEUE,
    )

    def __init__(self, *, max_size: int = DEFAULT_MAX_SIZE) -> None:
        self._items: deque[Track] = deque()
        self.max_size = max_size
        self.loop_mode: LoopMode = LoopMode.OFF

    def __len__(self) -> int:
        return len(self._items)

    def __bool__(self) -> bool:
        return bool(self._items)

    def __iter__(self) -> Iterator[Track]:
        return iter(self._items)

    def snapshot(self) -> list[Track]:
        return list(self._items)

    def add(self, track: Track) -> int:
        if len(self._items) >= self.max_size:
            raise QueueFullError(
                f"The queue is full (maximum {self.max_size} tracks)."
            )
        self._items.append(track)
        return len(self._items)

    def pop_next(self) -> Track | None:
        if not self._items:
            return None
        return self._items.popleft()

    def peek(self, position: int) -> Track:
        if not 1 <= position <= len(self._items):
            raise IndexError(
                f"Position {position} is out of range (1..{len(self._items)})."
            )
        return self._items[position - 1]

    def position_of(self, track: Track) -> int | None:
        for index, item in enumerate(self._items, start=1):
            if item is track:
                return index
        return None

    def remove_at(self, position: int) -> Track:
        if not 1 <= position <= len(self._items):
            raise IndexError(
                f"Position {position} is out of range (1..{len(self._items)})."
            )
        track = self._items[position - 1]
        del self._items[position - 1]
        return track

    def clear(self) -> int:
        count = len(self._items)
        self._items.clear()
        return count

    def shuffle(self) -> None:
        items = list(self._items)
        random.shuffle(items)
        self._items = deque(items)

    def total_duration(self) -> int:
        return sum(t.duration for t in self._items if t.duration > 0)

    def set_loop_mode(self, mode: LoopMode) -> None:
        self.loop_mode = mode

    def cycle_loop_mode(self) -> LoopMode:
        idx = (self._CYCLE_ORDER.index(self.loop_mode) + 1) % len(self._CYCLE_ORDER)
        self.loop_mode = self._CYCLE_ORDER[idx]
        return self.loop_mode
