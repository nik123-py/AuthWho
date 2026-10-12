"""Worker against the Compose PostgreSQL and Redis: windows, withdrawal and retention."""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from server.collector.repository import PostgresRepository
from server.common.redis_keys import EVENTS_STREAM
from server.db import retention
from server.worker.consumer import GROUP, run_once
from server.worker.store import PgWindowStore, WindowRecord, decrypt_features

pytestmark = pytest.mark.integration

KEY = os.urandom(32)


def _user(conn, opt_outs=(), exempt=False):
    uid = uuid.uuid4()
    conn.execute(
        "INSERT INTO users (user_id, app_id, role, consent_version, consent_at, opt_outs, exempt) "
        "VALUES (%s, 'demo', 'analyst', '1', now(), %s, %s)",
        (uid, list(opt_outs), exempt),
    )
    sid = uuid.uuid4()
    conn.execute(
        "INSERT INTO sessions (session_id, user_id, app_id, role) VALUES (%s, %s, 'demo', 'analyst')",
        (sid, uid),
    )
    return str(uid), str(sid)


def _xadd_presses(client, session_id, stream_id, n):
    for seq in range(n // 25):
        events = []
        for k in range(seq * 25, seq * 25 + 25):
            events += [[1, k * 120.0, 1, k], [2, k * 120.0 + 70.0, 1, k]]
        client.xadd(EVENTS_STREAM, {"session_id": session_id, "stream_id": stream_id,
                                    "seq": str(seq), "received_at": "2026-10-12T12:00:00.000Z",
                                    "pointer_device": "touchpad", "events": json.dumps(events)})


def _record(user_id, session_id, channel="keystroke"):
    return WindowRecord(
        window_id=str(uuid.uuid4()), session_id=session_id, stream_id=str(uuid.uuid4()),
        user_id=user_id, channel=channel, pointer_device="mouse", schema="kf-1",
        start_t=0.0, end_t=1.0, n_actions=50, quality=1.0, features_enc=b"\x01" + b"0" * 40,
        extractor_version="kf-1.0",
    )


def test_consumer_writes_encrypted_windows_and_acks(pg_conn, pg_url, redis_client):
    uid, sid = _user(pg_conn)
    stream = str(uuid.uuid4())
    _xadd_presses(redis_client, sid, stream, 100)
    written = run_once(redis_client, PgWindowStore(pg_url), KEY)
    assert written == 3
    rows = pg_conn.execute(
        "SELECT window_id, user_id, stream_id, channel, pointer_device, n_actions, features_enc "
        "FROM windows ORDER BY start_t").fetchall()
    assert len(rows) == 3
    wid, ruid, rstream, channel, device, n, blob = rows[0]
    assert (str(ruid), str(rstream), channel, device, n) == (uid, stream, "keystroke", "touchpad", 50)
    values = decrypt_features(bytes(blob), KEY, str(wid))
    assert len(values) == 35
    assert b"dwell" not in bytes(blob)
    assert redis_client.xpending(EVENTS_STREAM, GROUP)["pending"] == 0


def test_opted_out_user_gets_no_windows(pg_conn, pg_url, redis_client):
    _uid, sid = _user(pg_conn, opt_outs=["keystroke"])
    _xadd_presses(redis_client, sid, str(uuid.uuid4()), 100)
    assert run_once(redis_client, PgWindowStore(pg_url), KEY) == 0
    assert pg_conn.execute("SELECT count(*) FROM windows").fetchone()[0] == 0


def test_insert_is_refused_for_withdrawn_opted_out_or_exempt_users(pg_conn, pg_url):
    store = PgWindowStore(pg_url)
    uid, sid = _user(pg_conn)
    assert store.insert_window(_record(uid, sid)) is True
    out_uid, out_sid = _user(pg_conn, opt_outs=["keystroke"])
    assert store.insert_window(_record(out_uid, out_sid)) is False
    ex_uid, ex_sid = _user(pg_conn, exempt=True)
    assert store.insert_window(_record(ex_uid, ex_sid)) is False
    assert store.insert_window(_record(str(uuid.uuid4()), str(uuid.uuid4()))) is False
    assert pg_conn.execute("SELECT count(*) FROM windows").fetchone()[0] == 1


def test_withdrawal_deletes_the_users_windows(pg_conn, pg_url):
    store = PgWindowStore(pg_url)
    uid, sid = _user(pg_conn)
    other_uid, other_sid = _user(pg_conn)
    store.insert_window(_record(uid, sid))
    store.insert_window(_record(other_uid, other_sid))
    PostgresRepository(pg_url).delete_user(uid)
    remaining = [str(r[0]) for r in pg_conn.execute("SELECT user_id FROM windows").fetchall()]
    assert remaining == [other_uid]


def test_windows_older_than_30_days_are_deleted(pg_conn, pg_url):
    store = PgWindowStore(pg_url)
    uid, sid = _user(pg_conn)
    now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
    ages = {"old": timedelta(days=30, seconds=1), "young": timedelta(days=29, hours=23)}
    ids = {}
    for name, age in ages.items():
        rec = _record(uid, sid)
        store.insert_window(rec)
        pg_conn.execute("UPDATE windows SET created_at = %s WHERE window_id = %s",
                        (now - age, rec.window_id))
        ids[name] = rec.window_id
    assert retention.run_rule(pg_conn, retention.delete_expired_windows, now) == 1
    left = [str(r[0]) for r in pg_conn.execute("SELECT window_id FROM windows").fetchall()]
    assert left == [ids["young"]]
    assert retention.WINDOW_RETENTION == timedelta(days=30)
    assert retention.delete_expired_windows in retention.DB_RULES
