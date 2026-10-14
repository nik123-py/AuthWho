"""Users and sessions in PostgreSQL (docs/interfaces.md section 12).

``PostgresRepository`` is the production implementation. ``MemoryRepository``
has the same behaviour for unit tests; both pass ``tests/test_repository.py``.
Neither stores any behavioural data.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from server.common.db import Connector

# Tables holding per-user behavioural data, deleted with the user on consent
# withdrawal. Later phases append "profiles" and "trust_points".
USER_DATA_TABLES: list[str] = ["windows", "profiles", "trust_points"]


@dataclass(frozen=True)
class UserRecord:
    user_id: str
    app_id: str
    role: str
    consent_version: str
    consent_at: datetime
    research_consent: bool
    opt_outs: list[str]
    exempt: bool
    pointer_device: str
    # Set by the repository: when the current research consent was given.
    research_consent_at: datetime | None = None


def _research_consent_at(previous: UserRecord | None, user: UserRecord,
                         now: datetime) -> datetime | None:
    if not user.research_consent:
        return None
    if previous is not None and previous.research_consent:
        return previous.research_consent_at
    return now


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    user_id: str
    app_id: str
    role: str
    status: str
    created_at: datetime
    ended_at: datetime | None


class MemoryRepository:
    """In-process repository with the same semantics as ``PostgresRepository``. Tests only."""

    def __init__(self):
        self.users: dict[str, UserRecord] = {}
        self.sessions: dict[str, SessionRecord] = {}

    def upsert_user(self, user: UserRecord, now: datetime | None = None) -> UserRecord | None:
        previous = self.users.get(user.user_id)
        exempt = previous.exempt if previous else False
        consent_at = _research_consent_at(previous, user, now or datetime.now(timezone.utc))
        self.users[user.user_id] = replace(user, exempt=exempt, opt_outs=list(user.opt_outs),
                                           research_consent_at=consent_at)
        return previous

    def get_user(self, user_id: str) -> UserRecord | None:
        return self.users.get(user_id)

    def set_exempt(self, user_id: str, exempt: bool) -> None:
        if user_id in self.users:
            self.users[user_id] = replace(self.users[user_id], exempt=exempt)

    def delete_user(self, user_id: str) -> list[str]:
        self.users.pop(user_id, None)
        ids = []
        for sid, s in self.sessions.items():
            if s.user_id == user_id:
                ids.append(sid)
                if s.ended_at is None:
                    self.sessions[sid] = replace(s, status="terminated",
                                                 ended_at=datetime.now(timezone.utc))
        return ids

    def end_session(self, session_id: str) -> bool:
        s = self.sessions.get(session_id)
        if s is None:
            return False
        if s.ended_at is None:
            self.sessions[session_id] = replace(s, status="terminated",
                                                ended_at=datetime.now(timezone.utc))
        return True

    def create_session(self, session_id: str, user_id: str, app_id: str, role: str) -> None:
        self.sessions[session_id] = SessionRecord(session_id, user_id, app_id, role, "active",
                                                  datetime.now(timezone.utc), None)

    def get_session(self, session_id: str) -> SessionRecord | None:
        return self.sessions.get(session_id)


_USER_COLUMNS = ("user_id, app_id, role, consent_version, consent_at, research_consent, "
                 "opt_outs, exempt, pointer_device, research_consent_at")


def _user_from_row(row: dict) -> UserRecord:
    return UserRecord(**dict(row, user_id=str(row["user_id"]), opt_outs=list(row["opt_outs"])))


class PostgresRepository:
    """Opens a short-lived connection per call; request volume on these endpoints is low."""

    def __init__(self, conninfo: str):
        self.conninfo = conninfo
        self._connector = Connector(conninfo, row_factory=dict_row)

    def _connect(self):
        return self._connector()

    def upsert_user(self, user: UserRecord, now: datetime | None = None) -> UserRecord | None:
        """Create or update a user. ``now`` stamps a newly given research consent; the API
        passes its own clock, the same one that stamps ``received_at`` on batches."""
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {_USER_COLUMNS} FROM users WHERE user_id = %s FOR UPDATE", (user.user_id,)
            ).fetchone()
            previous = _user_from_row(row) if row else None
            consent_at = _research_consent_at(previous, user, now or datetime.now(timezone.utc))
            conn.execute(
                "INSERT INTO users (user_id, app_id, role, consent_version, consent_at, "
                "research_consent, research_consent_at, opt_outs, pointer_device) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (user_id) DO UPDATE SET app_id = EXCLUDED.app_id, "
                "role = EXCLUDED.role, consent_version = EXCLUDED.consent_version, "
                "consent_at = EXCLUDED.consent_at, research_consent = EXCLUDED.research_consent, "
                "research_consent_at = EXCLUDED.research_consent_at, "
                "opt_outs = EXCLUDED.opt_outs, pointer_device = EXCLUDED.pointer_device",
                (user.user_id, user.app_id, user.role, user.consent_version, user.consent_at,
                 user.research_consent, consent_at, list(user.opt_outs), user.pointer_device),
            )
        return previous

    def get_user(self, user_id: str) -> UserRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {_USER_COLUMNS} FROM users WHERE user_id = %s", (user_id,)
            ).fetchone()
        return _user_from_row(row) if row else None

    def set_exempt(self, user_id: str, exempt: bool) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE users SET exempt = %s WHERE user_id = %s", (exempt, user_id))

    def delete_user(self, user_id: str) -> list[str]:
        with self._connect() as conn:
            # The users row goes first: writers such as the feature worker lock it
            # (FOR KEY SHARE) before inserting, so no row can be added after this.
            conn.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
            for table in USER_DATA_TABLES:
                conn.execute(
                    sql.SQL("DELETE FROM {} WHERE user_id = %s").format(sql.Identifier(table)),
                    (user_id,),
                )
            conn.execute(
                "UPDATE sessions SET status = 'terminated', ended_at = now() "
                "WHERE user_id = %s AND ended_at IS NULL",
                (user_id,),
            )
            rows = conn.execute(
                "SELECT session_id FROM sessions WHERE user_id = %s", (user_id,)
            ).fetchall()
        return [str(r["session_id"]) for r in rows]

    def create_session(self, session_id: str, user_id: str, app_id: str, role: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (session_id, user_id, app_id, role) VALUES (%s, %s, %s, %s)",
                (session_id, user_id, app_id, role),
            )

    def end_session(self, session_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "UPDATE sessions SET status = 'terminated', ended_at = coalesce(ended_at, now()) "
                "WHERE session_id = %s RETURNING session_id",
                (session_id,),
            ).fetchone()
        return row is not None

    def get_session(self, session_id: str) -> SessionRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT session_id, user_id, app_id, role, status, created_at, ended_at "
                "FROM sessions WHERE session_id = %s",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        return SessionRecord(**dict(row, session_id=str(row["session_id"]),
                                    user_id=str(row["user_id"])))
