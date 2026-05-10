"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

import dotenv

_TRUE_VALUES = frozenset({"1", "true", "yes", "y", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "n", "off"})


def _get_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    raise RuntimeError(f"Invalid boolean for {key}: {raw!r}")


def _get_float(key: str, default: float, *, lo: float, hi: float) -> float:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid float for {key}: {raw!r}") from exc
    if not lo <= value <= hi:
        raise RuntimeError(f"{key}={value} out of range [{lo}, {hi}]")
    return value


def _get_int(key: str, default: int, *, lo: int = 0) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid integer for {key}: {raw!r}") from exc
    if value < lo:
        raise RuntimeError(f"{key}={value} must be >= {lo}")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    token: str
    skip_vote_ratio: float
    admin_instant_skip: bool
    requester_instant_skip: bool
    inactivity_timeout: int
    empty_channel_grace: int
    log_level: str
    activity_name: str
    ydl_force_ipv4: bool

    @classmethod
    def load(cls) -> Settings:
        dotenv.load_dotenv()
        token = os.getenv("DISCORD_TOKEN")
        if not token:
            raise RuntimeError(
                "DISCORD_TOKEN is not set. Create a .env file (see .env.example) "
                "and set the token."
            )
        return cls(
            token=token,
            skip_vote_ratio=_get_float("SKIP_VOTE_RATIO", 0.5, lo=0.0, hi=1.0),
            admin_instant_skip=_get_bool("ADMIN_INSTANT_SKIP", True),
            requester_instant_skip=_get_bool("REQUESTER_INSTANT_SKIP", True),
            inactivity_timeout=_get_int("INACTIVITY_TIMEOUT", 180, lo=10),
            empty_channel_grace=_get_int("EMPTY_CHANNEL_GRACE", 30, lo=0),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            activity_name=os.getenv("ACTIVITY_NAME", "").strip(),
            ydl_force_ipv4=_get_bool("YDL_FORCE_IPV4", True),
        )
