"""Shared fixtures for the demo backend tests.

The AuthWho collector is replaced by an in-process fake served through
``httpx.MockTransport``. The fake mirrors the responses documented in
``docs/interfaces.md`` sections 4 and 11 and records every request so tests
can check what the demo backend forwarded.
"""

import json
import re
import uuid
from dataclasses import dataclass, field

import httpx
import pytest
from fastapi.testclient import TestClient

from demo_app.backend.app import create_app
from demo_app.backend.config import Settings

COLLECTOR_URL = "http://collector.test:8000"
APP_KEY = "test-app-key-not-a-real-secret"
PASSWORD = "correct horse battery staple"


@dataclass
class RecordedRequest:
    method: str
    path: str
    headers: httpx.Headers
    body: dict | None


@dataclass
class FakeCollector:
    """Minimal stand-in for the AuthWho collector (sections 4 and 11)."""

    requests: list[RecordedRequest] = field(default_factory=list)
    consented_users: set[str] = field(default_factory=set)
    session_ids: list[str] = field(default_factory=list)
    stream_ids: list[str] = field(default_factory=list)
    fail_with: int | None = None
    unreachable: bool = False
    # Status for DELETE /v1/users/{id}; 404 means the user is already gone.
    user_delete_status: int = 204
    # Per-user faults for DELETE /v1/users/{id}: answer 500, or raise a non-HTTP error.
    failing_user_ids: set[str] = field(default_factory=set)
    crashing_user_ids: set[str] = field(default_factory=set)

    def calls(self, method: str, pattern: str) -> list[RecordedRequest]:
        regex = re.compile(pattern)
        return [r for r in self.requests if r.method == method and regex.fullmatch(r.path)]

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.requests.append(
            RecordedRequest(request.method, request.url.path, request.headers, body)
        )
        if self.unreachable:
            raise httpx.ConnectError("connection refused", request=request)
        if self.fail_with is not None:
            return httpx.Response(self.fail_with, json={"error": "unavailable"})
        if request.headers.get("X-AuthWho-App-Key") != APP_KEY:
            return httpx.Response(401, json={"error": "bad_app_key"})

        path = request.url.path
        if m := re.fullmatch(r"/v1/users/([0-9a-f-]+)", path):
            if request.method == "PUT":
                self.consented_users.add(m.group(1))
                return httpx.Response(200, json={"user_id": m.group(1)})
            if request.method == "DELETE":
                if m.group(1) in self.crashing_user_ids:
                    raise RuntimeError("unexpected fault inside the HTTP stack")
                if m.group(1) in self.failing_user_ids:
                    return httpx.Response(500, json={"error": "internal"})
                self.consented_users.discard(m.group(1))
                if self.user_delete_status != 204:
                    return httpx.Response(self.user_delete_status, json={"error": "not_found"})
                return httpx.Response(204)
        if path == "/v1/sessions" and request.method == "POST":
            if body["user_id"] not in self.consented_users:
                return httpx.Response(409, json={"error": "no_consent"})
            session_id = str(uuid.uuid4())
            self.session_ids.append(session_id)
            return httpx.Response(201, json={"session_id": session_id})
        if m := re.fullmatch(r"/v1/sessions/([0-9a-f-]+)/streams", path):
            stream_id = str(uuid.uuid4())
            self.stream_ids.append(stream_id)
            return httpx.Response(
                201,
                json={
                    "stream_id": stream_id,
                    "stream_key": "q83vEjRWeJq83vEjRWeJq83vEjRWeJq83vEjRWeJq80",
                    "expires_at": "2026-10-10T12:00:00Z",
                    "channels": {"keystroke": True, "pointer": False, "interaction": True},
                    "pointer_device": "touchpad",
                },
            )
        if re.fullmatch(r"/v1/sessions/([0-9a-f-]+)/end", path):
            return httpx.Response(200, json={"status": "terminated"})
        return httpx.Response(404, json={"error": "not_found"})


@pytest.fixture
def collector() -> FakeCollector:
    return FakeCollector()


@pytest.fixture
def db_path(tmp_path):
    # Nested folder so the tests also prove that parent folders are created.
    return tmp_path / "nested" / "demo" / "demo.sqlite"


def build_app(collector, db_path, retry_seconds: float = 300.0):
    """Build an app wired to the fake collector. Returns ``(app, http)``; close ``http`` after use."""
    settings = Settings(
        collector_url=COLLECTOR_URL,
        app_api_key=APP_KEY,
        db_path=db_path,
        withdrawal_retry_seconds=retry_seconds,
    )
    http = httpx.Client(transport=httpx.MockTransport(collector.handle))
    return create_app(settings=settings, collector_http=http), http


@pytest.fixture
def make_client(collector, db_path):
    """Start a fresh app instance on the same SQLite file, like a server restart."""
    opened = []

    def _make() -> TestClient:
        app, http = build_app(collector, db_path)
        test_client = TestClient(app)
        test_client.__enter__()
        opened.append((test_client, http))
        return test_client

    yield _make
    for test_client, http in opened:
        test_client.__exit__(None, None, None)
        http.close()


@pytest.fixture
def client(make_client):
    return make_client()


def register(client, username="alice", password=PASSWORD):
    return client.post("/api/register", json={"username": username, "password": password})


def login(client, username="alice", password=PASSWORD):
    return client.post("/api/login", json={"username": username, "password": password})


CONSENT_BODY = {
    "version": "1",
    "channels": {"keystroke": True, "pointer": False, "interaction": False},
    "research_consent": True,
    "pointer_device": "touchpad",
}


@pytest.fixture
def logged_in(client):
    assert register(client).status_code == 201
    assert login(client).status_code == 200
    return client


@pytest.fixture
def consented(logged_in):
    assert logged_in.post("/api/consent", json=CONSENT_BODY).status_code == 200
    return logged_in
