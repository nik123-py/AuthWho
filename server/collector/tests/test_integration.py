"""Collector against the Docker Compose PostgreSQL and Redis: C5 to C8."""

import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from server.api.app import create_app
from server.collector.hot_store import RedisHotStore
from server.collector.repository import PostgresRepository
from server.common.config import Settings
from server.common.redis_keys import EVENTS_STREAM
from server.common.testing import user_tables

from .helpers import APP_HEADERS, APP_KEY, open_stream, post_batch, put_user

pytestmark = pytest.mark.integration

MARKER_T = 98765.4  # a distinctive event value searched for in PostgreSQL


@pytest.fixture
def stack(pg_conn, pg_url, redis_client, tmp_path):
    repo = PostgresRepository(pg_url)
    app = create_app(settings=Settings(app_api_key=APP_KEY), hot_store=RedisHotStore(redis_client),
                     repository=repo, research_dir=tmp_path / "volunteer")
    with TestClient(app) as client:
        yield client, repo, pg_conn, redis_client


# ---- C5 ------------------------------------------------------------------------------------

def test_accepted_batch_is_in_aw_events_with_contract_fields(stack):
    client, _, _, r = stack
    _, sid, stream = open_stream(client)
    events = [[1, 1201.3, 1, 0], [2, 1288.9, 1, 0]]
    assert post_batch(client, sid, stream, seq=0, events=events).status_code == 202
    (_, fields), = r.xrange(EVENTS_STREAM)
    assert set(fields) == {"session_id", "stream_id", "seq", "received_at", "pointer_device", "events"}
    assert fields["session_id"] == sid and fields["stream_id"] == stream["stream_id"]
    assert fields["seq"] == "0" and fields["pointer_device"] == "mouse"
    assert json.loads(fields["events"]) == events
    assert fields["received_at"].endswith("Z")


def test_entry_older_than_24_hours_is_trimmed_by_next_xadd(stack):
    client, _, _, r = stack
    now_ms = int(time.time() * 1000)
    old_id = f"{now_ms - 24 * 3600 * 1000 - 60_000}-0"
    r.xadd(EVENTS_STREAM, {"seq": "old"}, id=old_id)
    _, sid, stream = open_stream(client)
    assert post_batch(client, sid, stream, seq=0).status_code == 202
    ids = [i for i, _ in r.xrange(EVENTS_STREAM)]
    assert old_id not in ids and len(ids) == 1


def test_stream_and_nonce_keys_expire_within_24_hours(stack):
    client, _, _, r = stack
    _, sid, stream = open_stream(client)
    post_batch(client, sid, stream, seq=0)
    day = 24 * 3600
    for key in (f"aw:stream:{stream['stream_id']}", f"aw:nonce:{stream['stream_id']}",
                f"aw:session:{sid}"):
        assert 0 < r.ttl(key) <= day, key


def test_stream_key_is_not_in_postgresql(stack):
    client, _, conn, _ = stack
    _, _, stream = open_stream(client)
    dump = _all_rows_text(conn)
    assert stream["stream_key"] not in dump


# ---- C6 ------------------------------------------------------------------------------------

def test_redis_has_no_disk_persistence(redis_client):
    assert redis_client.config_get("save")["save"] == ""
    assert redis_client.config_get("appendonly")["appendonly"] == "no"


# ---- C7 ------------------------------------------------------------------------------------

def _row_counts(conn):
    return {t: conn.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in user_tables(conn)}


def _all_rows_text(conn):
    parts = []
    for t in user_tables(conn):
        parts += [r[0] for r in conn.execute(f'SELECT row_to_json(x)::text FROM "{t}" x').fetchall()]
    return "\n".join(parts)


def test_no_postgresql_column_is_meant_for_events(pg_conn):
    rows = pg_conn.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND column_name ILIKE '%event%'"
    ).fetchall()
    assert rows == []


def test_batches_do_not_change_postgresql(stack):
    client, _, conn, r = stack
    _, sid, stream = open_stream(client)
    before = _row_counts(conn)
    assert before == {t: (1 if t in ("sessions", "users") else 0) for t in before}
    assert before["sessions"] == 1 and before["users"] == 1
    for seq in range(5):
        events = [[1, MARKER_T + seq, 1, seq], [2, MARKER_T + seq + 50, 1, seq]]
        assert post_batch(client, sid, stream, seq=seq, events=events).status_code == 202
    assert r.xlen(EVENTS_STREAM) == 5
    assert _row_counts(conn) == before
    assert "98765" not in _all_rows_text(conn)


# ---- C8 ------------------------------------------------------------------------------------

def test_consent_lifecycle_against_postgresql(stack):
    client, repo, conn, r = stack
    resp = client.post("/v1/sessions", json={"user_id": str(uuid.uuid4()), "app_id": "demo",
                                             "role": "analyst"}, headers=APP_HEADERS)
    assert resp.status_code == 409 and resp.json() == {"error": "no_consent"}

    uid, sid, stream = open_stream(client, opt_outs=["interaction"], pointer_device="touchpad")
    assert stream["channels"] == {"keystroke": True, "pointer": True, "interaction": False}
    assert stream["pointer_device"] == "touchpad"
    row = conn.execute("SELECT opt_outs, pointer_device FROM users WHERE user_id = %s",
                       (uid,)).fetchone()
    assert row == (["interaction"], "touchpad")

    repo.set_exempt(uid, True)
    exempt_stream = client.post(f"/v1/sessions/{sid}/streams", headers=APP_HEADERS).json()
    assert exempt_stream["channels"] == {"keystroke": False, "pointer": False, "interaction": False}

    assert post_batch(client, sid, stream, seq=0).status_code == 202
    assert client.delete(f"/v1/users/{uid}", headers=APP_HEADERS).status_code == 204
    assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 0
    assert conn.execute("SELECT status FROM sessions WHERE session_id = %s",
                        (sid,)).fetchone()[0] == "terminated"
    assert r.xlen(EVENTS_STREAM) == 0
    assert r.exists(f"aw:stream:{stream['stream_id']}") == 0
    assert post_batch(client, sid, stream, seq=1).json() == {"error": "unknown_stream"}


def test_put_user_is_idempotent_update(stack):
    client, _, conn, _ = stack
    uid = put_user(client)
    put_user(client, uid, research_consent=True, opt_outs=["pointer"])
    row = conn.execute("SELECT research_consent, opt_outs FROM users WHERE user_id = %s",
                       (uid,)).fetchone()
    assert row == (True, ["pointer"])
    assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 1


def test_end_session_against_postgresql_and_redis(stack):
    client, _, conn, r = stack
    _, sid, stream = open_stream(client)
    second = client.post(f"/v1/sessions/{sid}/streams", headers=APP_HEADERS).json()
    assert post_batch(client, sid, stream, seq=0).status_code == 202
    resp = client.post(f"/v1/sessions/{sid}/end", json={"reason": "logout"}, headers=APP_HEADERS)
    assert resp.json() == {"status": "terminated"}
    status, ended_at = conn.execute("SELECT status, ended_at FROM sessions WHERE session_id = %s",
                                    (sid,)).fetchone()
    assert status == "terminated" and ended_at is not None
    for s in (stream, second):
        assert r.exists(f"aw:stream:{s['stream_id']}", f"aw:nonce:{s['stream_id']}") == 0
    assert post_batch(client, sid, second, seq=0).json() == {"error": "unknown_stream"}
