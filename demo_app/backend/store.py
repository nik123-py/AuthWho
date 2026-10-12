"""SQLite storage for demo users, consent and login sessions.

The demo app keeps its own users, separate from AuthWho. Only the
pseudonymous ``authwho_user_id`` is ever shared with AuthWho. Free text
typed by users is never stored here.
"""

import hashlib
import secrets
import sqlite3
import threading
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROLE = "analyst"
CHANNELS = ("keystroke", "pointer", "interaction")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash BLOB NOT NULL,
    password_salt BLOB NOT NULL,
    authwho_user_id TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL,
    -- Consent fields are all NULL while the user has not consented.
    consent_version TEXT,
    consent_at TEXT,
    research_consent INTEGER,
    channel_keystroke INTEGER,
    channel_pointer INTEGER,
    channel_interaction INTEGER,
    pointer_device TEXT,
    -- 1 while a consent withdrawal has not yet been confirmed by AuthWho.
    withdrawal_pending INTEGER NOT NULL DEFAULT 0,
    -- TOTP secret, AES-256-GCM encrypted (demo_app/backend/totp.py); 1 once confirmed.
    totp_secret_enc BLOB,
    totp_enabled INTEGER NOT NULL DEFAULT 0
);

-- Login sessions. Only a SHA-256 digest of the opaque cookie token is kept,
-- so a copy of this file cannot be used to take over a login.
CREATE TABLE IF NOT EXISTS login_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    authwho_session_id TEXT,
    created_at TEXT NOT NULL,
    -- Wrong answers to the current step-up; three end the session.
    step_up_failures INTEGER NOT NULL DEFAULT 0
);
"""

_USER_COLUMNS = (
    "u.id, u.username, u.password_hash, u.password_salt, u.authwho_user_id, u.role,"
    " u.consent_version, u.consent_at, u.research_consent, u.channel_keystroke,"
    " u.channel_pointer, u.channel_interaction, u.pointer_device, u.withdrawal_pending,"
    " u.totp_secret_enc, u.totp_enabled"
)


class UsernameTaken(Exception):
    pass


@dataclass(frozen=True)
class Consent:
    version: str
    at: str
    channels: dict[str, bool]
    research_consent: bool
    pointer_device: str


@dataclass(frozen=True)
class User:
    id: int
    username: str
    password_hash: bytes
    password_salt: bytes
    authwho_user_id: str
    role: str
    consent: Consent | None
    withdrawal_pending: bool
    totp_secret_enc: bytes | None = None
    totp_enabled: bool = False


@dataclass(frozen=True)
class LoginSession:
    token_hash: str
    user: User
    authwho_session_id: str | None


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _user_from_row(row: sqlite3.Row) -> User:
    consent = None
    if row["consent_version"] is not None:
        consent = Consent(
            version=row["consent_version"],
            at=row["consent_at"],
            channels={name: bool(row[f"channel_{name}"]) for name in CHANNELS},
            research_consent=bool(row["research_consent"]),
            pointer_device=row["pointer_device"],
        )
    return User(
        id=row["id"],
        username=row["username"],
        password_hash=row["password_hash"],
        password_salt=row["password_salt"],
        authwho_user_id=row["authwho_user_id"],
        role=row["role"],
        consent=consent,
        withdrawal_pending=bool(row["withdrawal_pending"]),
        totp_secret_enc=row["totp_secret_enc"],
        totp_enabled=bool(row["totp_enabled"]),
    )


def _upgrade(conn: sqlite3.Connection) -> None:
    """Add columns introduced after a database file was first created."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    if "withdrawal_pending" not in columns:
        conn.execute(
            "ALTER TABLE users ADD COLUMN withdrawal_pending INTEGER NOT NULL DEFAULT 0"
        )
    if "totp_secret_enc" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN totp_secret_enc BLOB")
        conn.execute("ALTER TABLE users ADD COLUMN totp_enabled INTEGER NOT NULL DEFAULT 0")
    session_columns = {row[1] for row in conn.execute("PRAGMA table_info(login_sessions)")}
    if "step_up_failures" not in session_columns:
        conn.execute("ALTER TABLE login_sessions ADD COLUMN step_up_failures INTEGER NOT NULL DEFAULT 0")
    conn.commit()


class Store:
    def __init__(self, path: Path):
        self._path = Path(path)
        self._ready = False
        self._init_lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        if not self._ready:
            with self._init_lock:
                if not self._ready:
                    self._path.parent.mkdir(parents=True, exist_ok=True)
                    with closing(sqlite3.connect(self._path)) as conn:
                        conn.executescript(_SCHEMA)
                        _upgrade(conn)
                    self._ready = True
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # Users

    def create_user(self, username: str, password_hash: bytes, password_salt: bytes) -> User:
        with closing(self._connect()) as conn, conn:
            try:
                conn.execute(
                    "INSERT INTO users (username, password_hash, password_salt,"
                    " authwho_user_id, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (username, password_hash, password_salt, str(uuid.uuid4()), ROLE, now_iso()),
                )
            except sqlite3.IntegrityError as exc:
                raise UsernameTaken from exc
        return self.get_user(username)

    def get_user(self, username: str) -> User | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {_USER_COLUMNS} FROM users u WHERE u.username = ?", (username,)
            ).fetchone()
        return _user_from_row(row) if row else None

    # Consent

    def save_consent(self, user_id: int, consent: Consent) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE users SET consent_version = ?, consent_at = ?, research_consent = ?,"
                " channel_keystroke = ?, channel_pointer = ?, channel_interaction = ?,"
                " pointer_device = ? WHERE id = ?",
                (
                    consent.version,
                    consent.at,
                    int(consent.research_consent),
                    *(int(consent.channels[name]) for name in CHANNELS),
                    consent.pointer_device,
                    user_id,
                ),
            )

    def withdraw_consent(self, user_id: int) -> None:
        """Stop capture at once and remember that AuthWho still has to delete the user.

        In one transaction: clear the consent fields, so no stream can be
        minted; detach every login from its AuthWho session; and set the
        durable ``withdrawal_pending`` flag, cleared only once AuthWho confirms.
        """
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE users SET consent_version = NULL, consent_at = NULL,"
                " research_consent = NULL, channel_keystroke = NULL, channel_pointer = NULL,"
                " channel_interaction = NULL, pointer_device = NULL, withdrawal_pending = 1"
                " WHERE id = ?",
                (user_id,),
            )
            conn.execute(
                "UPDATE login_sessions SET authwho_session_id = NULL WHERE user_id = ?", (user_id,)
            )

    def pending_withdrawals(self) -> list[tuple[int, str]]:
        """Return ``(user id, authwho_user_id)`` for every unconfirmed withdrawal."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT id, authwho_user_id FROM users WHERE withdrawal_pending = 1 ORDER BY id"
            ).fetchall()
        return [(row["id"], row["authwho_user_id"]) for row in rows]

    def clear_withdrawal_pending(self, user_id: int) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("UPDATE users SET withdrawal_pending = 0 WHERE id = ?", (user_id,))

    # Login sessions

    def create_login_session(self, user: User) -> str:
        """Create a login session and return the opaque token for the cookie."""
        token = secrets.token_urlsafe(32)
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO login_sessions (token_hash, user_id, created_at) VALUES (?, ?, ?)",
                (_token_hash(token), user.id, now_iso()),
            )
        return token

    def get_login_session(self, token: str) -> LoginSession | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT s.token_hash, s.authwho_session_id, {_USER_COLUMNS}"
                " FROM login_sessions s JOIN users u ON u.id = s.user_id"
                " WHERE s.token_hash = ?",
                (_token_hash(token),),
            ).fetchone()
        if row is None:
            return None
        return LoginSession(row["token_hash"], _user_from_row(row), row["authwho_session_id"])

    def get_authwho_session_id(self, token_hash: str) -> str | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT authwho_session_id FROM login_sessions WHERE token_hash = ?", (token_hash,)
            ).fetchone()
        return row["authwho_session_id"] if row else None

    def set_authwho_session_id(self, token_hash: str, session_id: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE login_sessions SET authwho_session_id = ? WHERE token_hash = ?",
                (session_id, token_hash),
            )

    def delete_login_session(self, token_hash: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM login_sessions WHERE token_hash = ?", (token_hash,))

    # TOTP and step-up

    def set_totp_secret(self, user_id: int, secret_enc: bytes) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("UPDATE users SET totp_secret_enc = ?, totp_enabled = 0 WHERE id = ?", (secret_enc, user_id))

    def enable_totp(self, user_id: int) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("UPDATE users SET totp_enabled = 1 WHERE id = ? AND totp_secret_enc IS NOT NULL", (user_id,))

    def add_step_up_failure(self, token_hash: str) -> int:
        with closing(self._connect()) as conn, conn:
            conn.execute("UPDATE login_sessions SET step_up_failures = step_up_failures + 1 WHERE token_hash = ?",
                         (token_hash,))
            row = conn.execute("SELECT step_up_failures FROM login_sessions WHERE token_hash = ?",
                               (token_hash,)).fetchone()
        return int(row[0]) if row else 0

    def reset_step_up_failures(self, token_hash: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("UPDATE login_sessions SET step_up_failures = 0 WHERE token_hash = ?", (token_hash,))
