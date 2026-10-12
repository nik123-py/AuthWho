"""Contract tests run against both hot-state stores (memory and Redis)."""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from server.collector.hot_store import MemoryHotStore, RedisHotStore, StreamRecord
from server.common.redis_keys import EVENTS_STREAM


class FakeClock:
    def __init__(self):
        self.now = 1_000.0

    def __call__(self):
        return self.now


@pytest.fixture(params=["memory", pytest.param("redis", marks=pytest.mark.integration)])
def store(request):
    if request.param == "memory":
        return MemoryHotStore(rate_per_s=5, burst=20, clock=FakeClock())
    client = request.getfixturevalue("redis_client")
    return RedisHotStore(client, rate_per_s=5, burst=20)


def _stream(user_id="u1", session_id=None, channels=None):
    return StreamRecord(
        stream_id=str(uuid.uuid4()),
        session_id=session_id or str(uuid.uuid4()),
        user_id=user_id,
        stream_key="k" * 43,
        channels=channels or {"keystroke": True, "pointer": True, "interaction": True},
        pointer_device="mouse",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )


def _entry(rec, seq):
    return {"session_id": rec.session_id, "stream_id": rec.stream_id, "seq": str(seq),
            "received_at": "2026-10-09T12:00:00.000Z", "pointer_device": "mouse",
            "events": json.dumps([[10, 1.0, 1]])}


def test_created_stream_can_be_read_back(store):
    rec = _stream()
    store.create_stream(rec)
    got = store.get_stream(rec.stream_id)
    assert got.stream_key == rec.stream_key
    assert got.session_id == rec.session_id and got.user_id == rec.user_id
    assert got.channels == rec.channels
    assert store.get_stream(str(uuid.uuid4())) is None


def test_sequence_and_nonce_rules(store):
    rec = _stream()
    store.create_stream(rec)
    assert store.accept_batch(rec.stream_id, 0, "n0", _entry(rec, 0)) == "ok"
    assert store.accept_batch(rec.stream_id, 0, "n0", _entry(rec, 0)) == "duplicate"
    assert store.accept_batch(rec.stream_id, 0, "n9", _entry(rec, 0)) == "duplicate"
    assert store.accept_batch(rec.stream_id, 2, "n2", _entry(rec, 2)) == "out_of_order"
    assert store.accept_batch(rec.stream_id, 1, "n0", _entry(rec, 1)) == "nonce_reused"
    assert store.accept_batch(rec.stream_id, 1, "n1", _entry(rec, 1)) == "ok"
    assert store.accept_batch(str(uuid.uuid4()), 0, "x", _entry(rec, 0)) == "unknown_stream"


def test_accepted_batches_are_readable_and_rejected_are_not(store):
    rec = _stream()
    store.create_stream(rec)
    store.accept_batch(rec.stream_id, 0, "n0", _entry(rec, 0))
    store.accept_batch(rec.stream_id, 0, "n0", _entry(rec, 0))
    store.accept_batch(rec.stream_id, 1, "n1", None)  # accepted with nothing to store
    entries = store.read_events()
    assert [fields["seq"] for _, fields in entries] == ["0"]


def test_rate_limit_allows_burst_then_reports_retry_after(store):
    rec = _stream()
    store.create_stream(rec)
    results = [store.take_token(rec.stream_id) for _ in range(25)]
    assert all(r is None for r in results[:20])
    limited = [r for r in results if r is not None]
    assert limited and all(0 < r <= 1.0 for r in limited)


def test_ending_user_streams_makes_them_unknown_and_purges_their_events(store):
    mine = _stream(user_id="u1")
    other = _stream(user_id="u2")
    for rec in (mine, other):
        store.create_session_state(rec.session_id)
        store.create_stream(rec)
        store.accept_batch(rec.stream_id, 0, "n0", _entry(rec, 0))
    store.end_user_streams("u1", [mine.session_id])
    assert store.get_stream(mine.stream_id) is None
    assert store.accept_batch(mine.stream_id, 1, "n1", _entry(mine, 1)) == "unknown_stream"
    assert store.get_stream(other.stream_id) is not None
    assert [f["session_id"] for _, f in store.read_events()] == [other.session_id]
    assert store.session_status(mine.session_id) == "terminated"


def test_terminated_session_rejects_batches(store):
    rec = _stream()
    store.create_session_state(rec.session_id)
    store.create_stream(rec)
    assert store.session_status(rec.session_id) == "active"
    store.set_session_status(rec.session_id, "terminated")
    assert store.accept_batch(rec.stream_id, 0, "n0", _entry(rec, 0)) == "unknown_stream"


def test_set_user_channels_updates_live_streams_of_that_user_only(store):
    mine, other = _stream(user_id="u1"), _stream(user_id="u2")
    store.create_stream(mine)
    store.create_stream(other)
    store.set_user_channels("u1", {"keystroke": False, "pointer": True, "interaction": True})
    assert store.get_stream(mine.stream_id).channels["keystroke"] is False
    assert store.get_stream(other.stream_id).channels["keystroke"] is True


@pytest.mark.integration
def test_redis_ttls_are_at_most_24_hours(redis_client):
    store = RedisHotStore(redis_client)
    rec = _stream()
    store.create_session_state(rec.session_id)
    store.create_stream(rec)
    store.take_token(rec.stream_id)
    store.accept_batch(rec.stream_id, 0, "n0", _entry(rec, 0))
    day = 24 * 3600
    for key in (f"aw:stream:{rec.stream_id}", f"aw:nonce:{rec.stream_id}", f"aw:session:{rec.session_id}"):
        assert 0 < redis_client.ttl(key) <= day, key
    assert 0 < redis_client.ttl(f"aw:rate:{rec.stream_id}") <= 10
    assert redis_client.type(EVENTS_STREAM) == "stream"


def test_end_session_streams_removes_only_that_sessions_streams(store):
    mine = _stream(user_id="u1")
    second_page = _stream(user_id="u1", session_id=mine.session_id)
    other = _stream(user_id="u1")
    for rec in (mine, second_page, other):
        store.create_session_state(rec.session_id)
        store.create_stream(rec)
    store.accept_batch(mine.stream_id, 0, "n0", _entry(mine, 0))
    store.end_session_streams(mine.session_id)
    assert store.get_stream(mine.stream_id) is None
    assert store.get_stream(second_page.stream_id) is None
    assert store.get_stream(other.stream_id) is not None
    assert store.session_status(mine.session_id) == "terminated"
    assert store.accept_batch(mine.stream_id, 1, "n1", _entry(mine, 1)) == "unknown_stream"
    store.end_session_streams(mine.session_id)  # idempotent


@pytest.mark.integration
def test_end_session_streams_deletes_redis_hash_and_nonce_set(redis_client):
    store = RedisHotStore(redis_client)
    rec = _stream()
    store.create_session_state(rec.session_id)
    store.create_stream(rec)
    store.accept_batch(rec.stream_id, 0, "n0", _entry(rec, 0))
    assert redis_client.exists(f"aw:nonce:{rec.stream_id}") == 1
    store.end_session_streams(rec.session_id)
    assert redis_client.exists(f"aw:stream:{rec.stream_id}", f"aw:nonce:{rec.stream_id}") == 0
