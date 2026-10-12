"""PostgreSQL and Redis back ends for the scoring stage (docs/interfaces.md sections 7 and 9)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import psycopg
import redis
from psycopg.types.json import Jsonb

from server.common.crypto import decrypt, encrypt
from server.common.redis_keys import TRUST_CHANNEL, session_key
from server.worker.store import decrypt_features

SESSION_TTL_S = 24 * 3600


def encrypt_template(template: dict, key: bytes, profile_id: str) -> bytes:
    return encrypt(json.dumps(template).encode("utf-8"), key, aad=uuid.UUID(profile_id).bytes)


def decrypt_template(blob: bytes, key: bytes, profile_id: str) -> dict:
    return json.loads(decrypt(blob, key, aad=uuid.UUID(profile_id).bytes))


class PgScoringStore:
    def __init__(self, conninfo: str, key: bytes) -> None:
        self.conninfo = conninfo
        self.key = key

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.conninfo)

    def active_profile(self, user_id: str, channel: str, dkey: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT profile_id, template_enc FROM profiles WHERE user_id = %s AND channel = %s "
                "AND device_key = %s",
                (user_id, channel, dkey),
            ).fetchone()
        return decrypt_template(bytes(row[1]), self.key, str(row[0])) if row else None

    def enrollment_windows(self, user_id: str, channel: str, dkey: str, limit: int) -> list[tuple[list[float], float]]:
        query = ("SELECT window_id, features_enc, quality FROM windows WHERE user_id = %s AND channel = %s "
                 + ("" if dkey == "any" else "AND pointer_device = %s ")
                 + "ORDER BY created_at, window_id LIMIT %s")
        params = (user_id, channel, limit) if dkey == "any" else (user_id, channel, dkey, limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [(decrypt_features(bytes(enc), self.key, str(wid)), float(q)) for wid, enc, q in rows]

    def save_profile(self, user_id: str, channel: str, dkey: str, template: dict) -> bool:
        """Store a template, replacing any earlier version. False if the user is gone or opted out."""
        profile_id = str(uuid.uuid4())
        with self._connect() as conn, conn.transaction():
            row = conn.execute(
                "SELECT opt_outs, exempt FROM users WHERE user_id = %s FOR KEY SHARE", (user_id,)
            ).fetchone()
            if row is None or row[1] or channel in row[0]:
                return False
            old = conn.execute(
                "DELETE FROM profiles WHERE user_id = %s AND channel = %s AND device_key = %s RETURNING version",
                (user_id, channel, dkey),
            ).fetchone()
            conn.execute(
                "INSERT INTO profiles (profile_id, user_id, channel, device_key, version, model_kind, "
                "template_enc, n_windows) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (profile_id, user_id, channel, dkey, (old[0] + 1) if old else 1,
                 template["model"]["model_kind"], encrypt_template(template, self.key, profile_id),
                 template["n_windows"]),
            )
        return True

    def insert_trust_point(self, update: dict) -> None:
        with self._connect() as conn, conn.transaction():
            exists = conn.execute(
                "SELECT 1 FROM users WHERE user_id = %s FOR KEY SHARE", (update["user_id"],)
            ).fetchone()
            if exists is None:
                return
            conn.execute(
                "INSERT INTO trust_points (session_id, user_id, seq, at, state, trust, confidence, payload) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (update["session_id"], update["user_id"], update["seq"],
                 datetime.fromisoformat(update["at"].replace("Z", "+00:00")), update["state"],
                 update["trust"], update["confidence"], Jsonb(update)),
            )


class RedisTrustPublisher:
    """Publishes trust updates for the dashboard and keeps the latest in hot session state."""

    def __init__(self, client: redis.Redis) -> None:
        self.client = client

    def publish(self, update: dict) -> None:
        body = json.dumps(update)
        pipe = self.client.pipeline()
        pipe.publish(TRUST_CHANNEL, json.dumps({"type": "trust", "data": update}))
        pipe.hset(session_key(update["session_id"]), mapping={"last_trust": body})
        pipe.expire(session_key(update["session_id"]), SESSION_TTL_S)
        pipe.execute()
