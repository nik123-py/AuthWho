"""TOTP step-up for the demo app (proposal Section 12: pyotp, built in, no identity provider).

The secret is stored only encrypted with AES-256-GCM under ``DEMO_TOTP_KEY``,
with the user's pseudonymous AuthWho id as associated data, so a copy of the
SQLite file does not reveal it and a secret cannot be moved to another user.
Codes are checked with a window of one time step either side of now.
"""

from __future__ import annotations

import os
import uuid

import pyotp
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ISSUER = "AuthWho demo"


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, username: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=ISSUER)


def verify(secret: str, code: str) -> bool:
    code = (code or "").strip()
    return code.isdigit() and len(code) == 6 and pyotp.TOTP(secret).verify(code, valid_window=1)


def encrypt_secret(secret: str, key: bytes, authwho_user_id: str) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, secret.encode("ascii"), uuid.UUID(authwho_user_id).bytes)


def decrypt_secret(blob: bytes, key: bytes, authwho_user_id: str) -> str:
    return AESGCM(key).decrypt(blob[:12], blob[12:], uuid.UUID(authwho_user_id).bytes).decode("ascii")
