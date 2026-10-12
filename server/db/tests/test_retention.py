import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from server.db import retention

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)


def _session(conn, age: timedelta) -> uuid.UUID:
    sid = uuid.uuid4()
    conn.execute(
        "INSERT INTO sessions (session_id, user_id, app_id, role, created_at) "
        "VALUES (%s, %s, 'demo', 'analyst', %s)",
        (sid, uuid.uuid4(), NOW - age),
    )
    return sid


def _remaining(conn):
    return {r[0] for r in conn.execute("SELECT session_id FROM sessions").fetchall()}


def test_sessions_older_than_90_days_are_deleted_and_younger_kept(pg_conn):
    old = _session(pg_conn, timedelta(days=90, seconds=1))
    very_old = _session(pg_conn, timedelta(days=400))
    young = _session(pg_conn, timedelta(days=89, hours=23))
    fresh = _session(pg_conn, timedelta(0))
    deleted = retention.delete_expired_sessions(pg_conn, now=NOW)
    assert deleted == 2
    assert _remaining(pg_conn) == {young, fresh}
    assert old not in _remaining(pg_conn) and very_old not in _remaining(pg_conn)


def test_session_retention_is_90_days():
    assert retention.SESSION_RETENTION == timedelta(days=90)


def test_raw_events_older_than_24_hours_are_trimmed(redis_client):
    now_ms = int(time.time() * 1000)
    old_id = f"{now_ms - 24 * 3600 * 1000 - 1000}-0"
    young_id = f"{now_ms - 23 * 3600 * 1000}-0"
    redis_client.xadd("aw:events", {"seq": "0"}, id=old_id)
    redis_client.xadd("aw:events", {"seq": "1"}, id=young_id)
    removed = retention.trim_raw_events(redis_client, now_ms=now_ms)
    assert removed == 1
    assert [entry_id for entry_id, _ in redis_client.xrange("aw:events")] == [young_id]


def test_run_all_runs_every_rule_and_reports_counts_only(pg_conn, redis_client):
    _session(pg_conn, timedelta(days=200))
    counts = retention.run_all(pg_conn, redis_client)
    assert counts["delete_expired_sessions"] == 1
    assert counts["trim_raw_events"] == 0
    assert all(isinstance(v, int) for v in counts.values())


def test_database_rules_run_with_retention_setting_on(pg_conn):
    seen = {}

    def probe(conn, now=None):
        seen["value"] = conn.execute("SELECT current_setting('authwho.retention', true)").fetchone()[0]
        return 0

    retention.run_rule(pg_conn, probe)
    assert seen["value"] == "on"
    after = pg_conn.execute("SELECT current_setting('authwho.retention', true)").fetchone()[0]
    assert after in (None, "")
