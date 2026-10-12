"""D10: pending consent withdrawals are retried in the background, without any login.

A FastAPI lifespan task retries at startup and then every
``DEMO_WITHDRAWAL_RETRY_SECONDS`` (default 300). One failing user never stops
the others, and failures are logged by pseudonymous AuthWho user ID only.
"""

import logging
import sqlite3
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from demo_app.backend.authwho_client import CollectorClient
from demo_app.backend.config import Settings
from demo_app.backend.store import Store
from demo_app.backend.withdrawals import retry_pending_withdrawals

from .conftest import APP_KEY, COLLECTOR_URL, CONSENT_BODY, build_app, login, register

USER_PATH = r"/v1/users/[0-9a-f-]{36}"


def _make_pending(client, collector, username: str) -> str:
    """Register, consent and withdraw while AuthWho is down; return the AuthWho user ID."""
    assert register(client, username).status_code == 201
    assert login(client, username).status_code == 200
    assert client.post("/api/consent", json=CONSENT_BODY).status_code == 200
    collector.fail_with = 502
    assert client.delete("/api/consent").status_code == 502
    collector.fail_with = None
    with sqlite3.connect(client.app_db_path) as conn:
        return conn.execute(
            "SELECT authwho_user_id FROM users WHERE username = ?", (username,)
        ).fetchone()[0]


def _pending(db_path, username: str) -> bool:
    with sqlite3.connect(db_path) as conn:
        return bool(
            conn.execute(
                "SELECT withdrawal_pending FROM users WHERE username = ?", (username,)
            ).fetchone()[0]
        )


def _deletes_for(collector, authwho_user_id: str) -> int:
    return sum(1 for r in collector.calls("DELETE", USER_PATH) if r.path.endswith(authwho_user_id))


@pytest.fixture
def setup_client(client, db_path):
    client.app_db_path = db_path
    return client


@pytest.fixture
def run_once(collector, db_path):
    http = httpx.Client(transport=httpx.MockTransport(collector.handle))
    store = Store(db_path)
    authwho = CollectorClient(http, COLLECTOR_URL, APP_KEY)
    yield lambda: retry_pending_withdrawals(store, authwho)
    http.close()


# One run of the retry function


def test_one_run_clears_a_pending_user_without_any_login(setup_client, collector, db_path, run_once):
    authwho_id = _make_pending(setup_client, collector, "alice")
    assert _pending(db_path, "alice")

    run_once()

    assert _deletes_for(collector, authwho_id) == 2
    assert not _pending(db_path, "alice")


def test_one_run_with_nothing_pending_calls_nothing(setup_client, collector, run_once):
    register(setup_client)
    run_once()
    assert collector.requests == []


def test_404_during_background_run_clears_the_flag(setup_client, collector, db_path, run_once):
    _make_pending(setup_client, collector, "alice")
    collector.user_delete_status = 404
    run_once()
    assert not _pending(db_path, "alice")


def test_failing_user_does_not_stop_the_others(setup_client, collector, db_path, run_once, caplog):
    alice = _make_pending(setup_client, collector, "alice")
    _make_pending(setup_client, collector, "bob")
    _make_pending(setup_client, collector, "carol")
    collector.failing_user_ids = {alice}
    caplog.set_level(logging.DEBUG)

    run_once()

    assert _pending(db_path, "alice")
    assert not _pending(db_path, "bob")
    assert not _pending(db_path, "carol")
    assert alice in caplog.text
    for username in ("alice", "bob", "carol"):
        assert username not in caplog.text


def test_unexpected_error_for_one_user_does_not_stop_the_others(
    setup_client, collector, db_path, run_once, caplog
):
    alice = _make_pending(setup_client, collector, "alice")
    _make_pending(setup_client, collector, "bob")
    collector.crashing_user_ids = {alice}
    caplog.set_level(logging.DEBUG)

    run_once()

    assert _pending(db_path, "alice")
    assert not _pending(db_path, "bob")
    assert alice in caplog.text
    assert "alice" not in caplog.text and "bob" not in caplog.text


# Lifespan task


def _wait_until(condition, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


def test_startup_run_clears_pending_user_without_any_request(setup_client, collector, db_path):
    _make_pending(setup_client, collector, "alice")
    app, http = build_app(collector, db_path)
    try:
        with TestClient(app):  # startup only; no request is made
            assert _wait_until(lambda: not _pending(db_path, "alice"))
    finally:
        http.close()


def test_task_repeats_on_interval_and_stops_cleanly(setup_client, collector, db_path):
    alice = _make_pending(setup_client, collector, "alice")
    collector.failing_user_ids = {alice}
    app, http = build_app(collector, db_path, retry_seconds=0.05)
    try:
        before = _deletes_for(collector, alice)
        with TestClient(app):
            assert _wait_until(lambda: _deletes_for(collector, alice) >= before + 3)
        after_shutdown = _deletes_for(collector, alice)
        time.sleep(0.3)
        assert _deletes_for(collector, alice) == after_shutdown
    finally:
        http.close()


# Configuration


def test_retry_interval_defaults_to_300_seconds(monkeypatch):
    monkeypatch.delenv("DEMO_WITHDRAWAL_RETRY_SECONDS", raising=False)
    assert Settings.from_env().withdrawal_retry_seconds == 300.0


def test_retry_interval_is_read_from_environment(monkeypatch):
    monkeypatch.setenv("DEMO_WITHDRAWAL_RETRY_SECONDS", "45")
    assert Settings.from_env().withdrawal_retry_seconds == 45.0


@pytest.mark.parametrize("value", ["0", "-5", "soon"])
def test_invalid_retry_interval_is_rejected(monkeypatch, value):
    monkeypatch.setenv("DEMO_WITHDRAWAL_RETRY_SECONDS", value)
    with pytest.raises(ValueError, match="DEMO_WITHDRAWAL_RETRY_SECONDS"):
        Settings.from_env()


def test_settings_default_keeps_existing_callers_working():
    settings = Settings(collector_url=COLLECTOR_URL, app_api_key=APP_KEY, db_path=Path("x.sqlite"))
    assert settings.withdrawal_retry_seconds == 300.0
