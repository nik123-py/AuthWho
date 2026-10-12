"""Stream keys and batch signatures (docs/interfaces.md sections 4 and 6).

Stream keys and signatures are base64url without padding, matching the SDK.
Verification accepts either padded or unpadded signatures and compares in
constant time.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64url_decode(text: str) -> bytes:
    bare = text.rstrip("=")
    return base64.urlsafe_b64decode(bare + "=" * (-len(bare) % 4))


def new_stream_key() -> str:
    return b64url_encode(os.urandom(32))


def sign(stream_key: str, body: bytes) -> str:
    return b64url_encode(hmac.new(b64url_decode(stream_key), body, hashlib.sha256).digest())


def verify(stream_key: str, body: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    try:
        received = signature.strip().rstrip("=").encode("ascii")
    except UnicodeEncodeError:
        return False
    expected = sign(stream_key, body).encode("ascii")
    return hmac.compare_digest(expected, received)
