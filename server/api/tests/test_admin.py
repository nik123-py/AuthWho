"""Admin API and live WebSocket for the dashboard (docs/interfaces.md section 13)."""

import asyncio
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from server.api.app import create_app
from server.common.config import Settings

TOKEN = "admin-test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
SID = str(uuid.uuid4())


class FakeAdminRepo:
    def __init__(self):
        self.policy = {"policy_id": "demo-analyst", "app_id": "demo", "role": "analyst", "high": 75.0,
                       "strong": 50.0, "channel_low": 0.5, "action_sensitivity": {"add_payee": "high"},
                       "exempt": False, "version": 1}

    def list_sessions(self, limit):
        return [{"session_id": SID, "user_id": "u", "app_id": "demo", "role": "analyst", "status": "active",
                 "created_at": "2026-10-14T10:00:00+00:00", "ended_at": None, "trust": 64.0,
                 "state": "scored", "level": "moderate_deviation"}][:limit]

    def session(self, sid):
        return self.list_sessions(1)[0] if sid == SID else None

    def timeline(self, sid):
        return [{"seq": 1, "at": "2026-10-14T10:00:05Z", "state": "scored", "trust": 90.0, "confidence": 0.8,
                 "channels": {"keystroke": {"status": "scored", "score": 0.7, "top_features": []}}, "bot_flags": []},
                {"seq": 2, "at": "2026-10-14T10:00:20Z", "state": "scored", "trust": 64.0, "confidence": 0.9,
                 "channels": {"keystroke": {"status": "scored", "score": 0.1,
                                            "top_features": [{"name": "flight_median", "z": 5.2}]}},
                 "bot_flags": []}]

    def decisions(self, sid):
        return [{"decision_id": "d1", "created_at": "2026-10-14T10:00:20Z", "trigger": "trust_update",
                 "level": "moderate_deviation", "outcome": "monitor", "trust": 64.0,
                 "explanation": "Typing rhythm moved away from this user's profile, mainly the gap between keys."}]

    def policies(self):
        return [self.policy]

    def update_policy(self, policy_id, fields):
        if policy_id != "demo-analyst":
            return None
        self.policy = {**self.policy, **fields, "version": self.policy["version"] + 1}
        return self.policy


class FakeFeed:
    def __init__(self, messages):
        self.messages = messages

    async def subscribe(self):
        for m in self.messages:
            yield m
        await asyncio.sleep(3600)


@pytest.fixture
def client():
    settings = Settings(admin_token=TOKEN, app_api_key="k")
    feed = FakeFeed([json.dumps({"type": "trust", "data": {"session_id": SID, "trust": 64.0}}),
                     json.dumps({"type": "decision", "data": {"session_id": SID, "outcome": "monitor"}})])
    app = create_app(settings, hot_store=object(), repository=object(), session_control=object(),
                     policy_repo=object(), admin_repo=FakeAdminRepo(), trust_feed=feed)
    with TestClient(app) as c:
        yield c


def test_admin_endpoints_need_the_bearer_token(client):
    assert client.get("/v1/admin/sessions").status_code == 401
    assert client.get("/v1/admin/sessions", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/v1/admin/sessions", headers=AUTH).status_code == 200


def test_sessions_timeline_and_decisions(client):
    sessions = client.get("/v1/admin/sessions", headers=AUTH).json()
    assert sessions[0]["session_id"] == SID and sessions[0]["level"] == "moderate_deviation"
    timeline = client.get(f"/v1/admin/sessions/{SID}/timeline", headers=AUTH).json()
    assert [p["trust"] for p in timeline] == [90.0, 64.0]
    decisions = client.get(f"/v1/admin/sessions/{SID}/decisions", headers=AUTH).json()
    assert decisions[0]["explanation"].endswith(".")
    assert client.get(f"/v1/admin/sessions/{uuid.uuid4()}/timeline", headers=AUTH).status_code == 404


def test_incident_report_summarises_contributing_features(client):
    r = client.get(f"/v1/admin/sessions/{SID}/incident-report", headers=AUTH)
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    report = r.json()
    assert report["session"]["session_id"] == SID
    assert len(report["timeline"]) == 2 and len(report["decisions"]) == 1
    assert report["summary"]["lowest_trust"] == 64.0
    assert report["summary"]["contributing_features"][0] == {"channel": "keystroke", "name": "flight_median",
                                                             "times": 1, "max_abs_z": 5.2}


def test_policy_editor_validates_and_versions(client):
    assert client.get("/v1/admin/policies", headers=AUTH).json()[0]["high"] == 75.0
    ok = client.put("/v1/admin/policies/demo-analyst", headers=AUTH,
                    json={"high": 80, "strong": 45, "channel_low": 0.4,
                          "action_sensitivity": {"add_payee": "high", "export_report": "medium"}, "exempt": False})
    assert ok.status_code == 200 and ok.json()["version"] == 2 and ok.json()["high"] == 80
    bad = client.put("/v1/admin/policies/demo-analyst", headers=AUTH,
                     json={"high": 40, "strong": 50, "channel_low": 0.4, "action_sensitivity": {}, "exempt": False})
    assert bad.status_code == 400  # strong must be below high
    assert client.put("/v1/admin/policies/nope", headers=AUTH,
                      json={"high": 80, "strong": 45, "channel_low": 0.4, "action_sensitivity": {},
                            "exempt": False}).status_code == 404


def test_websocket_streams_trust_and_decisions_and_needs_the_token(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/v1/admin/ws?token=wrong") as ws:
            ws.receive_text()
    with client.websocket_connect(f"/v1/admin/ws?token={TOKEN}") as ws:
        first = json.loads(ws.receive_text())
        second = json.loads(ws.receive_text())
    assert (first["type"], second["type"]) == ("trust", "decision")


class BlockingFeed:
    """One message, then waits forever, like a quiet Redis channel."""

    def __init__(self):
        self.closed = False

    async def subscribe(self):
        try:
            yield json.dumps({"type": "trust", "data": {"session_id": SID}})
            await asyncio.sleep(3600)
        finally:
            self.closed = True


def test_websocket_subscription_closes_when_the_browser_disconnects():
    """Against a real uvicorn server: the test client cancels handlers itself, uvicorn does not."""
    import socket
    import threading
    import time

    import uvicorn
    from websockets.sync.client import connect

    feed = BlockingFeed()
    app = create_app(Settings(admin_token=TOKEN, app_api_key="k"), hot_store=object(), repository=object(),
                     session_control=object(), policy_repo=object(), admin_repo=FakeAdminRepo(), trust_feed=feed)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.time() + 10
        while not server.started and time.time() < deadline:
            time.sleep(0.05)
        with connect(f"ws://127.0.0.1:{port}/v1/admin/ws?token={TOKEN}") as ws:
            assert json.loads(ws.recv())["type"] == "trust"
        deadline = time.time() + 3
        while not feed.closed and time.time() < deadline:
            time.sleep(0.05)
        assert feed.closed, "the Redis subscription must be closed once the dashboard tab goes away"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
