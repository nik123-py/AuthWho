"""PostgreSQL access for policies and the append-only decisions table."""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from server.common.db import Connector
from server.policy.engine import DEFAULT_POLICY, Policy

_DECISION_COLUMNS = (
    "decision_id", "session_id", "user_id", "app_id", "role", "trigger", "action_code", "action_sensitivity",
    "level", "outcome", "action_allowed", "trust", "confidence", "channels", "bot_flags", "window_ids",
    "model_versions", "policy_version", "explanation", "step_up_result",
)
_JSON = {"channels", "bot_flags", "model_versions"}


class PgPolicyRepository:
    def __init__(self, conninfo: str) -> None:
        self.conninfo = conninfo
        self._connector = Connector(conninfo, row_factory=dict_row)

    def _connect(self):
        return self._connector()

    def load_policy(self, app_id: str, role: str) -> tuple[Policy, bool]:
        """The policy for an application and role, and whether the role is exempt."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM policies WHERE app_id = %s AND role = %s", (app_id, role)).fetchone()
        if row is None:
            return DEFAULT_POLICY, False
        policy = Policy(policy_id=row["policy_id"], version=f"{row['policy_id']}-v{row['version']}",
                        high=float(row["high"]), strong=float(row["strong"]),
                        channel_low=float(row["channel_low"]), action_sensitivity=dict(row["action_sensitivity"]))
        return policy, bool(row["exempt"])

    def session_context(self, session_id: str) -> dict[str, str] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT session_id, user_id, app_id, role FROM sessions WHERE session_id = %s",
                               (session_id,)).fetchone()
        return {k: str(v) for k, v in row.items()} if row else None

    def insert_decision(self, d: dict[str, Any]) -> None:
        values = [Jsonb(d[c]) if c in _JSON else d[c] for c in _DECISION_COLUMNS]
        cols = ", ".join(_DECISION_COLUMNS)
        marks = ", ".join(["%s"] * len(_DECISION_COLUMNS))
        with self._connect() as conn:
            conn.execute(f"INSERT INTO decisions ({cols}) VALUES ({marks})", values)

    def list_decisions(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM decisions WHERE session_id = %s ORDER BY created_at",
                                (session_id,)).fetchall()
        return [_jsonable(r) for r in rows]


def _jsonable(row: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in row.items():
        if k in ("decision_id", "session_id", "user_id"):
            v = str(v)
        elif k == "window_ids":
            v = [str(x) for x in v]
        elif k == "created_at":
            v = v.isoformat()
        out[k] = v
    return out
