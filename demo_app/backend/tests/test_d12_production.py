"""D12: production settings for the demo backend (login expiry, Secure cookie, public collector URL)."""

from datetime import datetime, timedelta, timezone

import httpx
from fastapi.testclient import TestClient

from demo_app.backend.app import create_app
from demo_app.backend.config import Settings
from demo_app.backend.tests.conftest import APP_KEY, COLLECTOR_URL, CONSENT_BODY, PASSWORD, TOTP_KEY


def _client(collector, db_path, **overrides):
    settings = Settings(collector_url=COLLECTOR_URL, app_api_key=APP_KEY, db_path=db_path, totp_key=TOTP_KEY,
                        **overrides)
    http = httpx.Client(transport=httpx.MockTransport(collector.handle))
    return TestClient(create_app(settings=settings, collector_http=http))


def _login(client):
    client.post("/api/register", json={"username": "alice", "password": PASSWORD})
    return client.post("/api/login", json={"username": "alice", "password": PASSWORD})


def test_secure_cookie_when_configured(collector, db_path):
    with _client(collector, db_path, secure_cookies=True) as c:
        cookie = _login(c).headers["set-cookie"].lower()
    assert "secure" in cookie and "httponly" in cookie and "samesite=lax" in cookie


def test_cookie_not_secure_by_default_for_local_http(collector, db_path):
    with _client(collector, db_path) as c:
        assert "secure" not in _login(c).headers["set-cookie"].lower()


def test_login_expires_after_the_configured_hours(collector, db_path):
    with _client(collector, db_path, session_hours=12) as c:
        _login(c)
        assert c.get("/api/me").status_code == 200
        import sqlite3
        with sqlite3.connect(db_path) as conn:
            old = (datetime.now(timezone.utc) - timedelta(hours=13)).isoformat(timespec="seconds")
            conn.execute("UPDATE login_sessions SET created_at = ?", (old,))
        assert c.get("/api/me").json() == {"error": "not_logged_in"}


def test_browser_gets_the_public_collector_url(collector, db_path):
    with _client(collector, db_path, public_collector_url="https://authwho.example.org") as c:
        _login(c)
        c.post("/api/consent", json=CONSENT_BODY)
        assert c.post("/api/authwho/stream").json()["endpoint"] == "https://authwho.example.org"
