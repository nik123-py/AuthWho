"""Password hashing with the standard library ``hashlib.scrypt``.

Each user gets a random 16-byte salt. Verification uses a constant-time
comparison. Passwords are never stored, logged or returned.
"""

import hashlib
import hmac
import secrets

SALT_BYTES = 16
_N = 2**14
_R = 8
_P = 1
_DKLEN = 64


def _derive(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)


def hash_password(password: str) -> tuple[bytes, bytes]:
    """Return ``(hash, salt)`` for a new password."""
    salt = secrets.token_bytes(SALT_BYTES)
    return _derive(password, salt), salt


def verify_password(password: str, stored_hash: bytes, salt: bytes) -> bool:
    return hmac.compare_digest(_derive(password, salt), stored_hash)


# Used when the username does not exist, so a failed login takes about as long
# whether or not the account exists.
_DUMMY_SALT = secrets.token_bytes(SALT_BYTES)
_DUMMY_HASH = _derive(secrets.token_urlsafe(16), _DUMMY_SALT)


def burn_time() -> None:
    verify_password("unused", _DUMMY_HASH, _DUMMY_SALT)
