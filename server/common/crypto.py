"""AES-256-GCM helpers shared by every AuthWho component.

Blob layout: one format byte (0x01), a 12-byte random nonce, then the GCM
ciphertext with its 16-byte tag. Optional associated data binds a blob to its
context (for example a session id) without storing that context in the blob.
"""

from __future__ import annotations

import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

FORMAT_V1 = b"\x01"
NONCE_BYTES = 12
KEY_BYTES = 32


class CryptoError(Exception):
    """Raised for a bad key, a malformed blob or a failed authentication check."""


def _check_key(key: bytes) -> None:
    if not isinstance(key, (bytes, bytearray)) or len(key) != KEY_BYTES:
        raise CryptoError("key must be exactly 32 bytes")


def encrypt(plaintext: bytes, key: bytes, aad: bytes | None = None) -> bytes:
    _check_key(key)
    nonce = os.urandom(NONCE_BYTES)
    return FORMAT_V1 + nonce + AESGCM(bytes(key)).encrypt(nonce, plaintext, aad)


def decrypt(blob: bytes, key: bytes, aad: bytes | None = None) -> bytes:
    _check_key(key)
    if len(blob) < 1 + NONCE_BYTES + 16 or blob[:1] != FORMAT_V1:
        raise CryptoError("malformed ciphertext")
    nonce = blob[1 : 1 + NONCE_BYTES]
    try:
        return AESGCM(bytes(key)).decrypt(nonce, blob[1 + NONCE_BYTES :], aad)
    except InvalidTag as exc:
        raise CryptoError("authentication failed") from exc
