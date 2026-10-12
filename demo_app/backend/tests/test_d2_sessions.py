"""D2: opaque login session cookie, logout and protected endpoints."""

import pytest

from .conftest import CONSENT_BODY, login, register

PROTECTED = [
    ("GET", "/api/me", None),
    ("POST", "/api/logout", None),
    ("POST", "/api/consent", CONSENT_BODY),
    ("DELETE", "/api/consent", None),
    ("POST", "/api/authwho/stream", None),
    ("POST", "/api/notes", {"text": "hello"}),
    ("POST", "/api/payees", {"name": "Bob", "account": "12345678"}),
    ("POST", "/api/reports/export", None),
]


def _set_cookie_header(response) -> str:
    headers = [v for k, v in response.headers.multi_items() if k.lower() == "set-cookie"]
    assert len(headers) == 1
    return headers[0]


def test_login_sets_httponly_samesite_lax_cookie(client):
    register(client)
    header = _set_cookie_header(login(client))
    attributes = [part.strip().lower() for part in header.split(";")]
    assert attributes[0].startswith("demo_session=")
    assert len(attributes[0]) > len("demo_session=") + 30
    assert "httponly" in attributes
    assert "samesite=lax" in attributes
    assert "path=/" in attributes


def test_session_token_is_opaque_and_new_on_each_login(client):
    register(client)
    first = login(client).cookies["demo_session"]
    second = login(client).cookies["demo_session"]
    assert first != second
    assert "alice" not in first and "alice" not in second


def test_raw_session_token_is_not_stored_in_database(client, db_path):
    register(client)
    token = login(client).cookies["demo_session"]
    assert token.encode() not in db_path.read_bytes()


def test_me_returns_username_and_null_consent_when_logged_in(logged_in):
    response = logged_in.get("/api/me")
    assert response.status_code == 200
    assert response.json() == {"username": "alice", "consent": None, "withdrawal_pending": False}


def test_logout_returns_204_and_invalidates_token(logged_in):
    token = logged_in.cookies["demo_session"]
    response = logged_in.post("/api/logout")
    assert response.status_code == 204
    logged_in.cookies.set("demo_session", token)
    assert logged_in.get("/api/me").status_code == 401


def test_logout_clears_cookie_in_browser(logged_in):
    header = _set_cookie_header(logged_in.post("/api/logout"))
    attributes = [part.strip().lower() for part in header.split(";")]
    assert attributes[0] in ('demo_session=""', "demo_session=")
    assert "max-age=0" in attributes


def test_logout_of_one_login_leaves_other_login_valid(client):
    register(client)
    first = login(client).cookies["demo_session"]
    second = login(client).cookies["demo_session"]
    client.cookies.set("demo_session", first)
    assert client.post("/api/logout").status_code == 204
    client.cookies.set("demo_session", second)
    assert client.get("/api/me").status_code == 200


@pytest.mark.parametrize(("method", "path", "body"), PROTECTED)
def test_protected_endpoint_without_cookie_returns_401(client, method, path, body):
    response = client.request(method, path, json=body)
    assert response.status_code == 401
    assert response.json() == {"error": "not_logged_in"}


@pytest.mark.parametrize(("method", "path", "body"), PROTECTED)
def test_protected_endpoint_with_forged_cookie_returns_401(client, method, path, body):
    register(client)
    client.cookies.set("demo_session", "forged-token-value-that-was-never-issued")
    assert client.request(method, path, json=body).status_code == 401
