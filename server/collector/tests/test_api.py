"""Collector API over HTTP with in-memory stores: C1 to C4 and C8 (unit level)."""

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from server.api.app import create_app
from server.collector.hot_store import MemoryHotStore
from server.collector.repository import MemoryRepository
from server.collector.signing import sign
from server.common.config import Settings

from .helpers import (
    APP_HEADERS,
    APP_KEY,
    batch_bytes,
    consent_body,
    new_nonce,
    open_stream,
    post_batch,
    post_raw,
    put_user,
)


class FakeClock:
    now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def env(tmp_path):
    hot = MemoryHotStore(rate_per_s=5, burst=20, clock=FakeClock())
    repo = MemoryRepository()
    settings = Settings(app_api_key=APP_KEY, cors_origins=("http://localhost:5173",))
    app = create_app(settings=settings, hot_store=hot, repository=repo,
                     research_dir=tmp_path / "volunteer")
    with TestClient(app) as client:
        yield client, hot, repo, tmp_path / "volunteer"


@pytest.fixture
def client(env):
    return env[0]


# ---- health and app key -------------------------------------------------------------------

def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


@pytest.mark.parametrize("headers", [{}, {"X-AuthWho-App-Key": "wrong"}])
def test_server_endpoints_require_app_key(client, headers):
    uid = str(uuid.uuid4())
    assert client.put(f"/v1/users/{uid}", json=consent_body(), headers=headers).status_code == 401
    assert client.delete(f"/v1/users/{uid}", headers=headers).status_code == 401
    r = client.post("/v1/sessions", json={"user_id": uid, "app_id": "demo", "role": "a"},
                    headers=headers)
    assert r.status_code == 401
    assert client.post(f"/v1/sessions/{uid}/streams", headers=headers).status_code == 401


# ---- C8 consent, sessions and streams ------------------------------------------------------

def test_put_user_creates_and_updates(env):
    client, _, repo, _ = env
    uid = str(uuid.uuid4())
    r = client.put(f"/v1/users/{uid}", json=consent_body(opt_outs=["interaction"],
                                                          pointer_device="touchpad"),
                   headers=APP_HEADERS)
    assert r.status_code == 200 and r.json() == {"user_id": uid}
    assert repo.get_user(uid).opt_outs == ["interaction"]
    put_user(client, uid, research_consent=True)
    assert repo.get_user(uid).research_consent is True


@pytest.mark.parametrize("body", [
    consent_body(extra="x"),
    consent_body(opt_outs=["typing-secret"]),
    consent_body(pointer_device="pen"),
    {"app_id": "demo"},
])
def test_put_user_rejects_bad_body_without_echoing_it(client, body):
    r = client.put(f"/v1/users/{uuid.uuid4()}", json=body, headers=APP_HEADERS)
    assert r.status_code == 400
    assert r.json()["error"] == "schema"
    assert "typing-secret" not in r.text and "pen" not in r.text.replace("open", "")


def test_session_without_consent_is_409(client):
    r = client.post("/v1/sessions", json={"user_id": str(uuid.uuid4()), "app_id": "demo",
                                          "role": "analyst"}, headers=APP_HEADERS)
    assert r.status_code == 409 and r.json() == {"error": "no_consent"}


def test_stream_handshake_returns_contract_fields(client):
    _, _, stream = open_stream(client, pointer_device="touchpad")
    assert set(stream) == {"stream_id", "stream_key", "expires_at", "channels", "pointer_device"}
    assert stream["channels"] == {"keystroke": True, "pointer": True, "interaction": True}
    assert stream["pointer_device"] == "touchpad"
    assert len(stream["stream_key"]) == 43 and "=" not in stream["stream_key"]


def test_stream_for_unknown_session_is_404(client):
    r = client.post(f"/v1/sessions/{uuid.uuid4()}/streams", headers=APP_HEADERS)
    assert r.status_code == 404 and r.json() == {"error": "unknown_session"}


def test_stream_channels_reflect_opt_outs(client):
    _, _, stream = open_stream(client, opt_outs=["interaction", "keystroke"])
    assert stream["channels"] == {"keystroke": False, "pointer": True, "interaction": False}


def test_stream_channels_all_off_for_exempt_user(env):
    client, _, repo, _ = env
    uid = put_user(client)
    repo.set_exempt(uid, True)
    r = client.post("/v1/sessions", json={"user_id": uid, "app_id": "demo", "role": "analyst"},
                    headers=APP_HEADERS)
    sid = r.json()["session_id"]
    stream = client.post(f"/v1/sessions/{sid}/streams", headers=APP_HEADERS).json()
    assert stream["channels"] == {"keystroke": False, "pointer": False, "interaction": False}


def test_events_of_disabled_channels_are_dropped_server_side(env):
    client, hot, _, _ = env
    _, sid, stream = open_stream(client, opt_outs=["keystroke"])
    r = post_batch(client, sid, stream, events=[[1, 1.0, 1, 0], [3, 2.0, 5, 6], [2, 3.0, 1, 0]])
    assert r.status_code == 202
    (_, fields), = hot.read_events()
    assert json.loads(fields["events"]) == [[3, 2.0, 5, 6]]


def test_opt_out_change_applies_to_live_streams(env):
    client, hot, _, _ = env
    uid, sid, stream = open_stream(client)
    put_user(client, uid, opt_outs=["pointer"])
    assert post_batch(client, sid, stream, events=[[3, 2.0, 5, 6]]).status_code == 202
    assert hot.read_events() == []


def test_delete_user_ends_streams_and_is_204(env):
    client, hot, repo, _ = env
    uid, sid, stream = open_stream(client)
    assert post_batch(client, sid, stream, seq=0).status_code == 202
    r = client.delete(f"/v1/users/{uid}", headers=APP_HEADERS)
    assert r.status_code == 204
    assert repo.get_user(uid) is None
    assert repo.get_session(sid).status == "terminated"
    assert hot.read_events() == []
    assert post_batch(client, sid, stream, seq=1).json() == {"error": "unknown_stream"}
    assert client.delete(f"/v1/users/{uid}", headers=APP_HEADERS).status_code == 204


def test_delete_user_removes_research_folder(env):
    client, _, _, research_dir = env
    uid = put_user(client, research_consent=True)
    folder = research_dir / uid
    folder.mkdir(parents=True)
    (folder / "x.bin").write_bytes(b"data")
    client.delete(f"/v1/users/{uid}", headers=APP_HEADERS)
    assert not folder.exists()


def test_withdrawing_research_consent_removes_research_folder(env):
    client, _, _, research_dir = env
    uid = put_user(client, research_consent=True)
    (research_dir / uid).mkdir(parents=True)
    put_user(client, uid, research_consent=False)
    assert not (research_dir / uid).exists()


# ---- batches: acceptance and C1 schema -----------------------------------------------------

def test_valid_batch_is_202(client):
    _, sid, stream = open_stream(client)
    r = post_batch(client, sid, stream)
    assert r.status_code == 202 and r.json() == {"accepted": True, "seq": 0}


def test_unknown_top_level_field_is_400(client):
    _, sid, stream = open_stream(client)
    r = post_batch(client, sid, stream, text="secret words")
    assert r.status_code == 400 and r.json()["error"] == "schema"
    assert "secret" not in r.text


@pytest.mark.parametrize("events", [
    [[99, 1.0, 1, 0]], [[1, 1.0, 1]], [[1, "a", 1, 0]], [[1, True, 1, 0]], [[1, None, 1, 0]],
])
def test_bad_events_are_400_without_echo(client, events):
    _, sid, stream = open_stream(client)
    r = post_batch(client, sid, stream, events=events)
    assert r.status_code == 400 and r.json()["error"] == "schema"
    assert "99" not in r.json()["detail"]


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_numbers_are_400(client, literal):
    _, sid, stream = open_stream(client)
    raw = batch_bytes(sid, stream).replace(b"1201.3", literal.encode())
    r = post_raw(client, raw, stream["stream_key"])
    assert r.status_code == 400 and r.json()["error"] == "schema"


def test_more_than_500_events_is_413(client):
    _, sid, stream = open_stream(client)
    r = post_batch(client, sid, stream, events=[[10, 1.0, 1]] * 501)
    assert r.status_code == 413 and r.json() == {"error": "too_large"}


def test_body_over_64_kib_is_413(client):
    _, sid, stream = open_stream(client)
    raw = batch_bytes(sid, stream, events=[[3, 123456.7, 12345, 12345]] * 500)
    raw = raw[:-1] + b" " * (65 * 1024 - len(raw)) + b"}"
    assert len(raw) > 64 * 1024
    r = post_raw(client, raw, stream["stream_key"])
    assert r.status_code == 413 and r.json() == {"error": "too_large"}


def test_session_id_must_match_stream(client):
    _, _, stream = open_stream(client)
    r = post_batch(client, str(uuid.uuid4()), stream)
    assert r.status_code == 400 and r.json()["error"] == "schema"


# ---- C2 signature --------------------------------------------------------------------------

def test_tampered_body_is_401_signature(client):
    _, sid, stream = open_stream(client)
    raw = batch_bytes(sid, stream)
    sig = sign(stream["stream_key"], raw)
    tampered = raw.replace(b"1201.3", b"1201.4")
    r = post_raw(client, tampered, None, signature=sig)
    assert r.status_code == 401 and r.json() == {"error": "signature"}


def test_wrong_key_is_401_signature(client):
    _, sid, stream = open_stream(client)
    _, _, other = open_stream(client)
    r = post_raw(client, batch_bytes(sid, stream), other["stream_key"])
    assert r.status_code == 401 and r.json() == {"error": "signature"}


def test_missing_signature_is_401(client):
    _, sid, stream = open_stream(client)
    r = client.post("/v1/batches", content=batch_bytes(sid, stream),
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 401 and r.json() == {"error": "signature"}


def test_unknown_stream_is_401(client):
    _, sid, stream = open_stream(client)
    fake = dict(stream, stream_id=str(uuid.uuid4()))
    r = post_raw(client, batch_bytes(sid, fake), stream["stream_key"])
    assert r.status_code == 401 and r.json() == {"error": "unknown_stream"}


# ---- C3 replay -----------------------------------------------------------------------------

def test_repeated_seq_is_duplicate(client):
    _, sid, stream = open_stream(client)
    raw = batch_bytes(sid, stream, seq=0)
    assert post_raw(client, raw, stream["stream_key"]).status_code == 202
    r = post_raw(client, raw, stream["stream_key"])
    assert r.status_code == 409 and r.json() == {"error": "replay", "reason": "duplicate"}


def test_skipped_seq_is_out_of_order(client):
    _, sid, stream = open_stream(client)
    assert post_batch(client, sid, stream, seq=0).status_code == 202
    r = post_batch(client, sid, stream, seq=2)
    assert r.status_code == 409 and r.json() == {"error": "replay", "reason": "out_of_order"}


def test_first_batch_must_be_seq_zero(client):
    _, sid, stream = open_stream(client)
    r = post_batch(client, sid, stream, seq=1)
    assert r.status_code == 409 and r.json()["reason"] == "out_of_order"


def test_reused_nonce_with_new_seq_is_nonce_reused(client):
    _, sid, stream = open_stream(client)
    nonce = new_nonce()
    assert post_batch(client, sid, stream, seq=0, nonce=nonce).status_code == 202
    r = post_batch(client, sid, stream, seq=1, nonce=nonce)
    assert r.status_code == 409 and r.json() == {"error": "replay", "reason": "nonce_reused"}


def test_rejected_batch_does_not_advance_seq(client):
    _, sid, stream = open_stream(client)
    assert post_batch(client, sid, stream, seq=0, events=[[99, 1.0]]).status_code == 400
    assert post_batch(client, sid, stream, seq=0).status_code == 202


# ---- C4 rate limit -------------------------------------------------------------------------

def test_rate_limit_is_429_with_retry_after(client):
    _, sid, stream = open_stream(client)
    codes = [post_batch(client, sid, stream, seq=i).status_code for i in range(20)]
    assert codes == [202] * 20
    r = post_batch(client, sid, stream, seq=20)
    assert r.status_code == 429
    body = r.json()
    assert body["error"] == "rate_limited" and body["retry_after"] > 0
    assert int(r.headers["Retry-After"]) >= 1


def test_rate_limit_refills_over_time(env):
    client, hot, _, _ = env
    _, sid, stream = open_stream(client)
    for i in range(20):
        post_batch(client, sid, stream, seq=i)
    assert post_batch(client, sid, stream, seq=20).status_code == 429
    hot.clock.now += 1.0
    assert post_batch(client, sid, stream, seq=20).status_code == 202


# ---- CORS ----------------------------------------------------------------------------------

def test_cors_preflight_allows_configured_origin_only(client):
    headers = {"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
               "Access-Control-Request-Headers": "content-type,x-authwho-signature"}
    r = client.options("/v1/batches", headers=headers)
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    r = client.options("/v1/batches", headers=dict(headers, Origin="http://evil.example"))
    assert "access-control-allow-origin" not in r.headers


# ---- session end (section 11) --------------------------------------------------------------

def test_end_session_stops_its_streams_and_is_idempotent(env):
    client, _, repo, _ = env
    _, sid, stream = open_stream(client)
    assert post_batch(client, sid, stream, seq=0).status_code == 202
    r = client.post(f"/v1/sessions/{sid}/end", json={"reason": "logout"}, headers=APP_HEADERS)
    assert r.status_code == 200 and r.json() == {"status": "terminated"}
    assert repo.get_session(sid).status == "terminated"
    r = post_batch(client, sid, stream, seq=1)
    assert r.status_code == 401 and r.json() == {"error": "unknown_stream"}
    again = client.post(f"/v1/sessions/{sid}/end", json={"reason": "logout"}, headers=APP_HEADERS)
    assert again.status_code == 200 and again.json() == {"status": "terminated"}
    r = client.post(f"/v1/sessions/{sid}/streams", headers=APP_HEADERS)
    assert r.status_code == 409 and r.json() == {"error": "session_ended"}


def test_end_session_checks_key_body_and_session(client):
    _, sid, _ = open_stream(client)
    url = f"/v1/sessions/{sid}/end"
    assert client.post(url, json={"reason": "logout"}).status_code == 401
    assert client.post(url, json={"reason": "logout", "x": 1}, headers=APP_HEADERS).status_code == 400
    assert client.post(url, json={}, headers=APP_HEADERS).status_code == 400
    r = client.post(f"/v1/sessions/{uuid.uuid4()}/end", json={"reason": "logout"},
                    headers=APP_HEADERS)
    assert r.status_code == 404 and r.json() == {"error": "unknown_session"}


# ---- research folder deletion must be verified ---------------------------------------------

@pytest.fixture
def stuck_folder(monkeypatch):
    from server.research import files
    monkeypatch.setattr(files, "RETRY_DELAY_S", 0)
    monkeypatch.setattr(files, "_rmtree", lambda path: None)
    return lambda: monkeypatch.setattr(files, "_rmtree", __import__("shutil").rmtree)


def test_delete_user_is_503_while_research_data_remains_then_204_on_retry(env, stuck_folder):
    client, _, repo, research_dir = env
    uid = put_user(client, research_consent=True)
    (research_dir / uid).mkdir(parents=True)
    (research_dir / uid / "s.bin").write_bytes(b"x")
    r = client.delete(f"/v1/users/{uid}", headers=APP_HEADERS)
    assert r.status_code == 503 and r.json() == {"error": "deletion_incomplete"}
    assert (research_dir / uid).exists()
    stuck_folder()  # the lock is released
    assert client.delete(f"/v1/users/{uid}", headers=APP_HEADERS).status_code == 204
    assert not (research_dir / uid).exists() and repo.get_user(uid) is None


def test_research_withdrawal_is_503_while_data_remains_and_retry_finishes(env, stuck_folder):
    client, _, _, research_dir = env
    uid = put_user(client, research_consent=True)
    (research_dir / uid).mkdir(parents=True)
    body = consent_body(research_consent=False)
    r = client.put(f"/v1/users/{uid}", json=body, headers=APP_HEADERS)
    assert r.status_code == 503 and r.json() == {"error": "deletion_incomplete"}
    stuck_folder()
    assert client.put(f"/v1/users/{uid}", json=body, headers=APP_HEADERS).status_code == 200
    assert not (research_dir / uid).exists()
