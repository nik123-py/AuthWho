"""Test helpers for driving the collector API. Test-only code."""

from __future__ import annotations

import base64
import json
import os
import uuid

from server.collector.signing import sign

APP_KEY = "test-app-key"
APP_HEADERS = {"X-AuthWho-App-Key": APP_KEY}


def consent_body(**overrides):
    body = {
        "app_id": "demo", "role": "analyst", "consent_version": "1",
        "consent_at": "2026-10-09T10:00:00+00:00", "research_consent": False,
        "opt_outs": [], "pointer_device": "mouse",
    }
    body.update(overrides)
    return body


def new_nonce() -> str:
    return base64.urlsafe_b64encode(os.urandom(16)).decode().rstrip("=")


def put_user(client, user_id=None, **overrides) -> str:
    user_id = user_id or str(uuid.uuid4())
    r = client.put(f"/v1/users/{user_id}", json=consent_body(**overrides), headers=APP_HEADERS)
    assert r.status_code == 200, r.text
    return user_id


def open_stream(client, **overrides):
    """Create a consented user, a session and a stream. Returns (user_id, session_id, stream)."""
    user_id = put_user(client, **overrides)
    r = client.post("/v1/sessions", json={"user_id": user_id, "app_id": "demo", "role": "analyst"},
                    headers=APP_HEADERS)
    assert r.status_code == 201, r.text
    session_id = r.json()["session_id"]
    r = client.post(f"/v1/sessions/{session_id}/streams", headers=APP_HEADERS)
    assert r.status_code == 201, r.text
    return user_id, session_id, r.json()


def batch_bytes(session_id, stream, seq=0, events=None, nonce=None, **extra) -> bytes:
    body = {
        "v": 1, "session_id": session_id, "stream_id": stream["stream_id"], "seq": seq,
        "nonce": nonce or new_nonce(), "sent_at": 2034.5, "pointer_device": "mouse",
        "events": events if events is not None else [[1, 1201.3, 1, 0], [2, 1288.9, 1, 0]],
    }
    body.update(extra)
    return json.dumps(body, separators=(",", ":")).encode()


def post_raw(client, raw: bytes, key: str | None, signature: str | None = None):
    headers = {"Content-Type": "application/json"}
    if signature is None and key is not None:
        signature = sign(key, raw)
    if signature is not None:
        headers["X-AuthWho-Signature"] = signature
    return client.post("/v1/batches", content=raw, headers=headers)


def post_batch(client, session_id, stream, **kwargs):
    return post_raw(client, batch_bytes(session_id, stream, **kwargs), stream["stream_key"])
