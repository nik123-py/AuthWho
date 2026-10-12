"""D8: no response contains a password or hash, and logs never contain passwords."""

import base64
import logging
import sqlite3

from .conftest import CONSENT_BODY, PASSWORD, login, register

STREAM_KEY = "q83vEjRWeJq83vEjRWeJq83vEjRWeJq83vEjRWeJq80"


def _secrets_of_alice(db_path) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        stored_hash, salt = conn.execute(
            "SELECT password_hash, password_salt FROM users WHERE username = 'alice'"
        ).fetchone()
    forms = [PASSWORD]
    for value in (stored_hash, salt):
        forms += [value.hex(), base64.b64encode(value).decode(), base64.urlsafe_b64encode(value).decode()]
    return forms


def test_full_flow_never_returns_password_or_hash_and_never_logs_secrets(client, collector, db_path, caplog):
    caplog.set_level(logging.DEBUG)
    responses = [
        register(client),
        register(client),  # duplicate, 409
        login(client, password="wrong password entirely"),
        login(client),
        client.get("/api/me"),
        client.post("/api/consent", json=CONSENT_BODY),
        client.get("/api/me"),
        client.post("/api/authwho/stream"),
        client.post("/api/payees", json={"name": "Bob", "account": "12345678"}),
        client.post("/api/reports/export"),
        client.delete("/api/consent"),
        client.post("/api/logout"),
        client.get("/api/me"),
    ]
    secrets_ = _secrets_of_alice(db_path)
    for response in responses:
        text = response.text + str(response.headers)
        for secret in secrets_:
            assert secret not in text, (response.request.url.path, response.status_code)
    for secret in secrets_:
        assert secret not in caplog.text
    assert "wrong password entirely" not in caplog.text
    assert STREAM_KEY not in caplog.text


def test_validation_error_does_not_echo_the_password(client, caplog):
    caplog.set_level(logging.DEBUG)
    response = client.post("/api/register", json={"username": "carol", "password": "tiny7"})
    assert response.status_code == 422
    assert "tiny7" not in response.text
    assert "tiny7" not in caplog.text


def test_validation_error_names_the_bad_field(client):
    response = client.post("/api/register", json={"username": "carol", "password": "tiny7"})
    assert response.json() == {"error": "invalid_request", "fields": ["password"]}


def test_validation_error_does_not_echo_note_text(logged_in):
    response = logged_in.post("/api/notes", json={"text": ["secret-list-item-4417"]})
    assert response.status_code == 422
    assert "secret-list-item-4417" not in response.text
