"""Session control in Redis hot state and PostgreSQL (docs/interfaces.md sections 7 and 11).

``aw:session:{session_id}`` holds ``status`` (``active``, ``step_up_required``
or ``terminated``), ``last_trust`` (written by the worker), ``last_decision_id``
and ``verified_at`` (epoch seconds of the last passed step-up). Ending a
session uses the collector's own path, so its stream keys stop working at once
exactly as on logout. Nothing here can disable or delete an account.
"""

from __future__ import annotations

import json
import time
from typing import Any

import redis

from server.collector.hot_store import RedisHotStore
from server.common.redis_keys import TRUST_CHANNEL, session_key

ACTIVE, STEP_UP, TERMINATED = "active", "step_up_required", "terminated"


class SessionControl:
    def __init__(self, client: redis.Redis, sessions_repo=None) -> None:
        self.client = client
        self.hot = RedisHotStore(client)
        self.sessions_repo = sessions_repo  # collector repository, to mark the sessions row ended

    def status(self, session_id: str) -> str | None:
        return self.client.hget(session_key(session_id), "status")

    def last_decision_id(self, session_id: str) -> str | None:
        return self.client.hget(session_key(session_id), "last_decision_id")

    def last_trust(self, session_id: str) -> dict[str, Any] | None:
        raw = self.client.hget(session_key(session_id), "last_trust")
        return json.loads(raw) if raw else None

    def verified_at(self, session_id: str) -> float | None:
        raw = self.client.hget(session_key(session_id), "verified_at")
        return float(raw) if raw else None

    def _set(self, session_id: str, mapping: dict[str, str]) -> None:
        key = session_key(session_id)
        if self.client.exists(key):
            self.client.hset(key, mapping=mapping)

    def publish_decision(self, decision: dict) -> None:
        self.client.publish(TRUST_CHANNEL, json.dumps({"type": "decision", "data": decision}))
        self._set(decision["session_id"], {"last_decision_id": decision["decision_id"]})

    def require_step_up(self, session_id: str, decision_id: str) -> None:
        if self.status(session_id) == ACTIVE:
            self._set(session_id, {"status": STEP_UP, "last_decision_id": decision_id})

    def mark_verified(self, session_id: str, decision_id: str, now: float | None = None) -> None:
        if self.status(session_id) != TERMINATED:
            self._set(session_id, {"status": ACTIVE, "verified_at": str(now if now is not None else time.time()),
                                   "last_decision_id": decision_id})

    def terminate(self, session_id: str, decision_id: str) -> None:
        self._set(session_id, {"last_decision_id": decision_id})
        self.hot.end_session_streams(session_id)
        if self.sessions_repo is not None:
            self.sessions_repo.end_session(session_id)
