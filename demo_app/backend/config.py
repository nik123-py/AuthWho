"""Configuration for the demo backend, read from environment variables.

Variables (see ``docs/interfaces.md`` section 3):

- ``AUTHWHO_COLLECTOR_URL``: AuthWho API base URL, default ``http://localhost:8000``.
- ``AUTHWHO_APP_API_KEY``: server-to-server key sent as ``X-AuthWho-App-Key``.
- ``DEMO_DB_PATH``: SQLite file for demo users, default ``data/demo/demo.sqlite``.
- ``DEMO_WITHDRAWAL_RETRY_SECONDS``: interval of the background retry of pending
  consent withdrawals, default 300.
- ``DEMO_TOTP_KEY``: 32-byte key, base64, encrypting stored TOTP secrets. Without
  it TOTP enrollment is unavailable and step-up asks for the password.
- ``DEMO_PUBLIC_COLLECTOR_URL``: the collector URL browsers use, when it differs
  from the internal ``AUTHWHO_COLLECTOR_URL`` (for example behind a reverse proxy).
- ``DEMO_SECURE_COOKIES``: ``true`` to mark the login cookie Secure (HTTPS deployments).
- ``DEMO_SESSION_HOURS``: hours before a login expires, default 12.

Secrets are never given defaults in source. Load them from ``.env``, for
example with ``uvicorn demo_app.backend.app:app --port 8100 --env-file .env``.
"""

import base64
import binascii
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_COLLECTOR_URL = "http://localhost:8000"
DEFAULT_DB_PATH = "data/demo/demo.sqlite"
DEFAULT_WITHDRAWAL_RETRY_SECONDS = 300.0


@dataclass(frozen=True)
class Settings:
    collector_url: str
    app_api_key: str
    db_path: Path
    withdrawal_retry_seconds: float = DEFAULT_WITHDRAWAL_RETRY_SECONDS
    totp_key: bytes | None = None
    public_collector_url: str | None = None
    secure_cookies: bool = False
    session_hours: float = 12.0

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            collector_url=os.environ.get("AUTHWHO_COLLECTOR_URL", DEFAULT_COLLECTOR_URL).rstrip("/"),
            app_api_key=os.environ.get("AUTHWHO_APP_API_KEY", ""),
            db_path=Path(os.environ.get("DEMO_DB_PATH", DEFAULT_DB_PATH)),
            withdrawal_retry_seconds=_positive_seconds("DEMO_WITHDRAWAL_RETRY_SECONDS"),
            totp_key=_optional_key("DEMO_TOTP_KEY"),
            public_collector_url=(os.environ.get("DEMO_PUBLIC_COLLECTOR_URL") or "").rstrip("/") or None,
            secure_cookies=os.environ.get("DEMO_SECURE_COOKIES", "").lower() in ("1", "true", "yes"),
            session_hours=float(os.environ.get("DEMO_SESSION_HOURS", "12")),
        )


def _positive_seconds(name: str) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return DEFAULT_WITHDRAWAL_RETRY_SECONDS
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{name} must be a number of seconds") from None
    if not value > 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _optional_key(name: str) -> bytes | None:
    raw = os.environ.get(name)
    if not raw:
        return None
    try:
        key = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError(f"{name} must be base64") from None
    if len(key) != 32:
        raise ValueError(f"{name} must decode to 32 bytes")
    return key
