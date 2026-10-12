"""Integration fixtures serialise concurrent pytest runs on the shared test databases.

The lock is a Redis key with a short TTL kept alive by a heartbeat, so a run
that is killed releases it within seconds (a PostgreSQL advisory lock could
stay held forever behind the Docker Desktop port proxy).
"""

import time
import uuid

import pytest
import redis

from server.common.testing import (
    LOCK_KEY,
    LOCK_TTL_MS,
    acquire_lock,
    lock_redis_url,
    release_lock,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def lock_client():
    client = redis.Redis.from_url(lock_redis_url(), decode_responses=True)
    yield client
    client.close()


def test_fixtures_hold_the_lock_with_a_short_ttl(redis_client, lock_client):
    assert lock_client.set(LOCK_KEY, "intruder", nx=True, px=1000) is None
    assert 0 < lock_client.pttl(LOCK_KEY) <= LOCK_TTL_MS


def test_lock_left_by_a_dead_run_expires_and_can_be_taken(lock_client):
    key = f"{LOCK_KEY}:probe:{uuid.uuid4()}"
    lock_client.set(key, "dead-run", px=300)  # a run that died without releasing
    start = time.monotonic()
    assert acquire_lock(lock_client, key, "me", ttl_ms=5000, wait_s=5)
    assert time.monotonic() - start < 3
    assert lock_client.get(key) == "me"
    release_lock(lock_client, key, "someone-else")  # only the owner may release
    assert lock_client.get(key) == "me"
    release_lock(lock_client, key, "me")
    assert lock_client.get(key) is None


def test_acquire_gives_up_after_the_wait(lock_client):
    key = f"{LOCK_KEY}:probe:{uuid.uuid4()}"
    lock_client.set(key, "busy", px=10_000)
    try:
        assert acquire_lock(lock_client, key, "me", ttl_ms=5000, wait_s=0.3) is False
    finally:
        lock_client.delete(key)


def test_lock_is_reentrant_within_one_process(redis_client, monkeypatch):
    # Each tests/conftest.py imports the fixtures, so pytest creates one session
    # fixture per folder. A second one in the same run must not wait for the first.
    from server.common import testing

    monkeypatch.setattr(testing, "LOCK_WAIT_S", 0.5)
    start = time.monotonic()
    with testing.integration_lock_held():
        assert time.monotonic() - start < 0.4
