"""Runtime patches for third-party dependencies."""

from __future__ import annotations

import logging
import struct
from functools import wraps
from typing import Any

import discord.voice_client as voice_client

try:
    from nacl.exceptions import CryptoError
    from nacl.secret import Aead
except (ImportError, AttributeError):  # pragma: no cover - runtime guard
    Aead = None  # type: ignore[assignment]
    CryptoError = Exception  # type: ignore[assignment]


_LOGGER = logging.getLogger(__name__)


def apply_voice_encryption_patch() -> None:
    """Extend :mod:`py-cord` voice support with modern encryption.

    Discord rolled out the ``aead_xchacha20_poly1305_rtpsize`` transport
    in late 2024. Versions of :mod:`py-cord` prior to the upstream patch only
    advertise ``xsalsa20``-based modes which causes the voice websocket to crash
    with ``IndexError`` when guilds require the new cipher.  To keep the bot
    working we monkey-patch :class:`discord.voice_client.VoiceClient` to include
    the new transport and provide minimal encrypt/decrypt helpers for it.
    """

    voice_cls = voice_client.VoiceClient

    if getattr(voice_cls, "_aead_patch_applied", False):
        return

    if Aead is None:
        _LOGGER.warning(
            "Cannot patch voice encryption because nacl.secret.Aead is unavailable."
        )
        return

    existing_modes = tuple(voice_cls.supported_modes)
    if "aead_xchacha20_poly1305_rtpsize" not in existing_modes:
        voice_cls.supported_modes = ("aead_xchacha20_poly1305_rtpsize",) + existing_modes

    original_init = voice_cls.__init__

    @wraps(original_init)
    def wrapped_init(self: voice_client.VoiceClient, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        # Counter reused by AEAD and lite modes.
        self._aead_nonce = 0  # type: ignore[attr-defined]

    voice_cls.__init__ = wrapped_init  # type: ignore[assignment]

    def _encrypt_aead_xchacha20_poly1305_rtpsize(
        self: voice_client.VoiceClient, header: bytes, data: Any
    ) -> bytes:
        nonce_value = getattr(self, "_aead_nonce", 0)
        nonce = bytearray(24)
        nonce[:4] = struct.pack(">I", nonce_value)
        self._aead_nonce = (nonce_value + 1) & 0xFFFFFFFF  # type: ignore[attr-defined]

        box = Aead(bytes(self.secret_key))
        encrypted = box.encrypt(bytes(data), bytes(header), bytes(nonce))
        return header + encrypted.ciphertext + nonce[:4]

    def _decrypt_aead_xchacha20_poly1305_rtpsize(
        self: voice_client.VoiceClient, header: bytes, data: bytes
    ) -> bytes:
        if len(data) < 4:
            return b""

        nonce = bytearray(24)
        nonce[:4] = data[-4:]
        ciphertext = data[:-4]

        box = Aead(bytes(self.secret_key))
        try:
            decrypted = box.decrypt(bytes(ciphertext), bytes(header), bytes(nonce))
        except CryptoError:
            return b""
        return self.strip_header_ext(decrypted)

    voice_cls._encrypt_aead_xchacha20_poly1305_rtpsize = (  # type: ignore[attr-defined]
        _encrypt_aead_xchacha20_poly1305_rtpsize
    )
    voice_cls._decrypt_aead_xchacha20_poly1305_rtpsize = (  # type: ignore[attr-defined]
        _decrypt_aead_xchacha20_poly1305_rtpsize
    )
    voice_cls._aead_patch_applied = True  # type: ignore[attr-defined]

    _LOGGER.info(
        "Patched py-cord voice client to support aead_xchacha20_poly1305_rtpsize."
    )

