"""PostgreSQL queries for the admin API."""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from server.common.db import Connector
from server.policy.repository import PgPolicyRepository

_SESSION_QUERY = """
SELECT s.session_id, s.user_id, s.app_id, s.role, s.status, s.created_at, s.ended_at,
       tp.trust, tp.state, d.level
FROM sessions s
LEFT JOIN LATERAL (SELECT trust, state FROM trust_points t WHERE t.session_id = s.session_id
                   ORDER BY seq DESC LIMIT 1) tp ON true
LEFT JOIN LATERAL (SELECT level FROM decisions x WHERE x.session_id = s.session_id
                   ORDER BY created_at DESC LIMIT 1) d ON true
"""


def _plain(row: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            v = v.isoformat()
        elif k in ("session_id", "user_id") and v is not None:
            v = str(v)
        out[k] = v
    return out


class PgAdminRepository:
    def __init__(self, conninfo: str) -> None:
        self.conninfo = conninfo
        self._connector = Connector(conninfo, row_factory=dict_row)
        self.decision_repo = PgPolicyRepository(conninfo)

    def _connect(self):
        return self._connector()

    def list_sessions(self, limit: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(_SESSION_QUERY + " ORDER BY s.created_at DESC LIMIT %s", (limit,)).fetchall()
        return [_plain(r) for r in rows]

    def session(self, session_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(_SESSION_QUERY + " WHERE s.session_id = %s", (session_id,)).fetchone()
        return _plain(row) if row else None

    def timeline(self, session_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT seq, at, state, trust, confidence, payload->'channels' AS channels, "
                "payload->'bot_flags' AS bot_flags FROM trust_points WHERE session_id = %s ORDER BY seq",
                (session_id,)).fetchall()
        return [_plain(r) for r in rows]

    def decisions(self, session_id: str) -> list[dict]:
        return self.decision_repo.list_decisions(session_id)

    def policies(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT policy_id, app_id, role, high, strong, channel_low, action_sensitivity, "
                                "exempt, version FROM policies ORDER BY policy_id").fetchall()
        return [_plain(r) for r in rows]

    def update_policy(self, policy_id: str, fields: dict) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "UPDATE policies SET high = %s, strong = %s, channel_low = %s, action_sensitivity = %s, "
                "exempt = %s, version = version + 1, updated_at = now() WHERE policy_id = %s "
                "RETURNING policy_id, app_id, role, high, strong, channel_low, action_sensitivity, exempt, version",
                (fields["high"], fields["strong"], fields["channel_low"], Jsonb(fields["action_sensitivity"]),
                 fields["exempt"], policy_id)).fetchone()
        return _plain(row) if row else None
