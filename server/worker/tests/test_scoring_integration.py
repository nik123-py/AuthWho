"""Worker with scoring against the Compose PostgreSQL and Redis."""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from server.collector.repository import PostgresRepository
from server.common.redis_keys import EVENTS_STREAM, TRUST_CHANNEL, session_key
from server.db import retention
from server.worker.consumer import run_once
from server.worker.pipeline import FeaturePipeline
from server.worker.scoring import TrustScorer
from server.worker.scoring_store import PgScoringStore, RedisTrustPublisher, decrypt_template
from server.worker.store import PgWindowStore

from server.worker.tests.test_integration import _user

pytestmark = pytest.mark.integration

KEY = os.urandom(32)


def _xadd_typing(client, session_id, stream_id, n_batches, rhythm=1.0, start_seq=0):
    for seq in range(start_seq, start_seq + n_batches):
        events = []
        for k in range(seq * 25, seq * 25 + 25):
            gap = (110.0 + 15.0 * (k % 4)) * rhythm
            hold = (70.0 + 5.0 * (k % 3)) * rhythm
            cat = 3 if k % 6 == 5 else 1
            events += [[1, k * gap, cat, k], [2, k * gap + hold, cat, k]]
        client.xadd(EVENTS_STREAM, {"session_id": session_id, "stream_id": stream_id, "seq": str(seq),
                                    "received_at": "2026-10-12T12:00:00.000Z", "pointer_device": "mouse",
                                    "events": json.dumps(events)})


def _pipeline(pg_url, redis_client, enroll=5):
    scorer = TrustScorer(PgScoringStore(pg_url, KEY), RedisTrustPublisher(redis_client), enroll_windows=enroll)
    return FeaturePipeline(PgWindowStore(pg_url), KEY, on_window=scorer.on_window), scorer


def test_enrollment_scoring_storage_and_publish(pg_conn, pg_url, redis_client):
    uid, sid = _user(pg_conn)
    pubsub = redis_client.pubsub()
    pubsub.subscribe(TRUST_CHANNEL)
    pipe, _ = _pipeline(pg_url, redis_client)
    stream = str(uuid.uuid4())
    _xadd_typing(redis_client, sid, stream, 12)  # 300 presses: 11 windows
    run_once(redis_client, None, None, pipeline=pipe)

    prof = pg_conn.execute("SELECT profile_id, channel, device_key, version, n_windows, template_enc "
                           "FROM profiles WHERE user_id = %s", (uid,)).fetchall()
    assert len(prof) == 1
    pid, channel, dkey, version, n, enc = prof[0]
    assert (channel, dkey, version, n) == ("keystroke", "any", 1, 5)
    assert b"calibration" not in bytes(enc) and b"scaled_manhattan" not in bytes(enc)
    template = decrypt_template(bytes(enc), KEY, str(pid))
    assert template["channel"] == "keystroke" and template["n_windows"] == 5

    rows = pg_conn.execute("SELECT seq, state, trust, payload FROM trust_points WHERE session_id = %s ORDER BY seq",
                           (sid,)).fetchall()
    assert len(rows) == 11
    assert [r[1] for r in rows[:5]] == ["insufficient_signal"] * 5
    assert all(r[1] == "scored" and r[2] is not None for r in rows[5:])
    assert rows[-1][3]["channels"]["keystroke"]["status"] == "scored"

    hot = json.loads(redis_client.hget(session_key(sid), "last_trust"))
    assert hot["seq"] == rows[-1][0]
    messages = []
    for _ in range(40):
        m = pubsub.get_message(timeout=0.2)
        if m and m["type"] == "message":
            messages.append(json.loads(m["data"]))
    assert len(messages) == 11 and messages[0]["type"] == "trust"
    pubsub.close()


def test_a_different_typist_lowers_trust(pg_conn, pg_url, redis_client):
    uid, sid = _user(pg_conn)
    pipe, _ = _pipeline(pg_url, redis_client)
    stream = str(uuid.uuid4())
    _xadd_typing(redis_client, sid, stream, 8)  # enrol on 7 windows (first 5 used)
    run_once(redis_client, None, None, pipeline=pipe)
    _xadd_typing(redis_client, sid, stream, 10, rhythm=1.9, start_seq=8)  # much slower, longer holds
    run_once(redis_client, None, None, pipeline=pipe)
    last = pg_conn.execute("SELECT trust FROM trust_points WHERE session_id = %s ORDER BY seq DESC LIMIT 1",
                           (sid,)).fetchone()
    assert last[0] < 50


def test_withdrawal_and_retention_delete_profiles_and_trust_points(pg_conn, pg_url, redis_client):
    uid, sid = _user(pg_conn)
    pipe, _ = _pipeline(pg_url, redis_client)
    _xadd_typing(redis_client, sid, str(uuid.uuid4()), 8)
    run_once(redis_client, None, None, pipeline=pipe)
    assert pg_conn.execute("SELECT count(*) FROM profiles WHERE user_id = %s", (uid,)).fetchone()[0] == 1

    now = datetime.now(timezone.utc)
    pg_conn.execute("UPDATE trust_points SET created_at = %s WHERE session_id = %s AND seq = 1",
                    (now - timedelta(days=31), sid))
    assert retention.run_rule(pg_conn, retention.delete_expired_trust_points, now) == 1
    assert retention.delete_expired_trust_points in retention.DB_RULES

    PostgresRepository(pg_url).delete_user(uid)
    for table in ("profiles", "trust_points", "windows"):
        assert pg_conn.execute(f"SELECT count(*) FROM {table} WHERE user_id = %s", (uid,)).fetchone()[0] == 0


def test_no_profile_is_saved_for_an_opted_out_channel(pg_conn, pg_url):
    uid, _ = _user(pg_conn, opt_outs=("keystroke",))
    store = PgScoringStore(pg_url, KEY)
    assert store.save_profile(uid, "keystroke", "any", {"model": {"model_kind": "scaled_manhattan"}, "n_windows": 5}) is False
