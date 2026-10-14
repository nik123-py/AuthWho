"""Window storage for the feature worker (docs/interfaces.md section 8).

Feature values are encrypted with AES-256-GCM under ``AUTHWHO_DATA_KEY``. The
window id's 16 bytes are the associated data, so a ciphertext cannot be moved
to another row without failing authentication.

``PgWindowStore.insert_window`` locks the user's row (``FOR KEY SHARE``) in
the same transaction as the insert and checks consent, opt-outs and exemption
there. A withdrawal deletes the ``users`` row before the user's windows (see
``server/collector/repository.py``), so a concurrent insert either finishes
first and is then deleted with the rest, or waits and finds no user.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Protocol

import psycopg

from server.common.db import Connector
from server.common.crypto import decrypt, encrypt


@dataclass(frozen=True)
class UserContext:
    user_id: str
    opt_outs: tuple[str, ...]
    exempt: bool

    def allows(self, channel: str) -> bool:
        return not self.exempt and channel not in self.opt_outs


@dataclass(frozen=True)
class WindowRecord:
    window_id: str
    session_id: str
    stream_id: str
    user_id: str
    channel: str
    pointer_device: str
    schema: str
    start_t: float
    end_t: float
    n_actions: int
    quality: float
    features_enc: bytes
    extractor_version: str


class WindowStore(Protocol):
    def user_context(self, session_id: str) -> UserContext | None: ...

    def insert_window(self, rec: WindowRecord) -> bool: ...


def encrypt_features(values: list[float], key: bytes, window_id: str) -> bytes:
    return encrypt(json.dumps(values).encode("utf-8"), key, aad=uuid.UUID(window_id).bytes)


def decrypt_features(blob: bytes, key: bytes, window_id: str) -> list[float]:
    return json.loads(decrypt(blob, key, aad=uuid.UUID(window_id).bytes))


class PgWindowStore:
    def __init__(self, conninfo: str) -> None:
        self.conninfo = conninfo
        self._connector = Connector(conninfo)

    def _connect(self):
        return self._connector()

    def user_context(self, session_id: str) -> UserContext | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT u.user_id, u.opt_outs, u.exempt FROM sessions s "
                "JOIN users u ON u.user_id = s.user_id WHERE s.session_id = %s",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return UserContext(str(row[0]), tuple(row[1]), bool(row[2]))

    def insert_window(self, rec: WindowRecord) -> bool:
        with self._connect() as conn, conn.transaction():
            row = conn.execute(
                "SELECT opt_outs, exempt FROM users WHERE user_id = %s FOR KEY SHARE",
                (rec.user_id,),
            ).fetchone()
            if row is None or not UserContext(rec.user_id, tuple(row[0]), bool(row[1])).allows(rec.channel):
                return False
            conn.execute(
                "INSERT INTO windows (window_id, session_id, stream_id, user_id, channel, "
                "pointer_device, schema, start_t, end_t, n_actions, quality, features_enc, "
                "extractor_version) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (rec.window_id, rec.session_id, rec.stream_id, rec.user_id, rec.channel,
                 rec.pointer_device, rec.schema, rec.start_t, rec.end_t, rec.n_actions,
                 rec.quality, rec.features_enc, rec.extractor_version),
            )
        return True
