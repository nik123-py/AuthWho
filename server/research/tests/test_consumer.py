"""C10 (consumer): only research-consented users get files; deletion removes them."""

import json
import os
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from server.research.consumer import GROUP, export_entries, pg_consent_lookup, run_once
from server.research.files import read_session_file, session_file, user_dir

KEY = os.urandom(32)
CONSENTED = datetime(2026, 10, 9, 11, 0, tzinfo=timezone.utc)  # before the batches' 12:00


def _fields(session_id, seq, events=None, received_at="2026-10-09T12:00:00.000Z"):
    return {"session_id": session_id, "stream_id": str(uuid.uuid4()), "seq": str(seq),
            "received_at": received_at, "pointer_device": "mouse",
            "events": json.dumps(events or [[1, 1201.3, 1, seq]])}


def test_only_research_consented_users_are_exported(tmp_path):
    yes_user, no_user = str(uuid.uuid4()), str(uuid.uuid4())
    yes_sid, no_sid, gone_sid = (str(uuid.uuid4()) for _ in range(3))
    consent = {yes_sid: (yes_user, CONSENTED), no_sid: (no_user, None)}
    entries = [("1-0", _fields(yes_sid, 0)), ("2-0", _fields(no_sid, 0)),
               ("3-0", _fields(gone_sid, 0)), ("4-0", _fields(yes_sid, 1))]
    written = export_entries(entries, consent.get, KEY, tmp_path)
    assert written == 2
    assert [p.name for p in tmp_path.iterdir()] == [yes_user]
    batches = read_session_file(session_file(tmp_path, yes_user, yes_sid), KEY)
    assert [b["seq"] for b in batches] == [0, 1]
    assert batches[0]["events"] == [[1, 1201.3, 1, 0]]


def test_batches_received_before_research_consent_are_never_exported(tmp_path):
    uid, sid = str(uuid.uuid4()), str(uuid.uuid4())
    consent_at = datetime(2026, 10, 9, 12, 0, 0, 500000, tzinfo=timezone.utc)
    entries = [
        ("1-0", _fields(sid, 0, received_at="2026-10-09T11:59:59.999Z")),
        ("2-0", _fields(sid, 1, received_at="2026-10-09T12:00:00.499Z")),
        ("3-0", _fields(sid, 2, received_at="2026-10-09T12:00:00.500Z")),
        ("4-0", _fields(sid, 3, received_at="2026-10-09T13:00:00.000Z")),
        ("5-0", _fields(sid, 4, received_at="not a time")),
    ]
    written = export_entries(entries, {sid: (uid, consent_at)}.get, KEY, tmp_path)
    assert written == 2
    batches = read_session_file(session_file(tmp_path, uid, sid), KEY)
    assert [b["seq"] for b in batches] == [2, 3]


def test_consent_withdrawn_during_write_removes_the_folder(tmp_path):
    uid, sid = str(uuid.uuid4()), str(uuid.uuid4())
    answers = iter([(uid, CONSENTED), None])
    export_entries([("1-0", _fields(sid, 0))], lambda _sid: next(answers), KEY, tmp_path)
    assert not user_dir(tmp_path, uid).exists()


@pytest.mark.integration
def test_end_to_end_export_through_api_and_consumer_group(pg_conn, pg_url, redis_client, tmp_path):
    from server.api.app import create_app
    from server.collector.hot_store import RedisHotStore
    from server.collector.repository import PostgresRepository
    from server.collector.tests.helpers import APP_HEADERS, APP_KEY, open_stream, post_batch
    from server.common.config import Settings

    base = tmp_path / "volunteer"
    app = create_app(settings=Settings(app_api_key=APP_KEY), hot_store=RedisHotStore(redis_client),
                     repository=PostgresRepository(pg_url), research_dir=base)
    with TestClient(app) as client:
        yes_uid, yes_sid, yes_stream = open_stream(client, research_consent=True)
        no_uid, no_sid, no_stream = open_stream(client, research_consent=False)
        events = [[1, 1201.3, 1, 0], [2, 1288.9, 1, 0]]
        for seq in range(2):
            assert post_batch(client, yes_sid, yes_stream, seq=seq, events=events).status_code == 202
            assert post_batch(client, no_sid, no_stream, seq=seq, events=events).status_code == 202

        lookup = pg_consent_lookup(pg_url)
        assert run_once(redis_client, lookup, KEY, base) == 2
        assert run_once(redis_client, lookup, KEY, base) == 0
        assert redis_client.xpending("aw:events", GROUP)["pending"] == 0

        assert user_dir(base, yes_uid).exists()
        assert not user_dir(base, no_uid).exists()
        path = session_file(base, yes_uid, yes_sid)
        assert [b["events"] for b in read_session_file(path, KEY)] == [events, events]
        assert b"1201.3" not in path.read_bytes()

        assert client.delete(f"/v1/users/{yes_uid}", headers=APP_HEADERS).status_code == 204
        assert not user_dir(base, yes_uid).exists()


@pytest.mark.integration
def test_batches_from_before_consent_stay_unexported_even_if_consumer_was_down(
        pg_conn, pg_url, redis_client, tmp_path):
    from server.api.app import create_app
    from server.collector.hot_store import RedisHotStore
    from server.collector.repository import PostgresRepository
    from server.collector.tests.helpers import APP_KEY, open_stream, post_batch, put_user
    from server.common.config import Settings

    base = tmp_path / "volunteer"
    app = create_app(settings=Settings(app_api_key=APP_KEY), hot_store=RedisHotStore(redis_client),
                     repository=PostgresRepository(pg_url), research_dir=base)
    with TestClient(app) as client:
        uid, sid, stream = open_stream(client, research_consent=False)
        assert post_batch(client, sid, stream, seq=0).status_code == 202  # before consent
        put_user(client, uid, research_consent=True)
        assert post_batch(client, sid, stream, seq=1).status_code == 202  # after consent
        # The consumer only runs now, after both batches arrived.
        assert run_once(redis_client, pg_consent_lookup(pg_url), KEY, base) == 1
        batches = read_session_file(session_file(base, uid, sid), KEY)
        assert [b["seq"] for b in batches] == [1]


@pytest.mark.integration
def test_consumer_client_survives_a_block_longer_than_five_seconds(redis_client, tmp_path):
    # redis-py 8 times out socket reads after 5 s by default, which broke the
    # blocking read in main(). make_client must allow for the block.
    from server.common.testing import redis_url_for_tests
    from server.research.consumer import BLOCK_MS, make_client

    assert BLOCK_MS >= 5000
    client = make_client(redis_url_for_tests())
    try:
        assert run_once(client, lambda _sid: None, KEY, tmp_path, block_ms=5500) == 0
    finally:
        client.close()


def test_failed_withdrawal_deletion_is_remembered_and_retried(tmp_path, monkeypatch):
    import shutil

    from server.research import files
    from server.research.consumer import retry_deletions

    monkeypatch.setattr(files, "RETRY_DELAY_S", 0)
    monkeypatch.setattr(files, "_rmtree", lambda path: None)  # folder locked
    uid, sid = str(uuid.uuid4()), str(uuid.uuid4())
    answers = iter([(uid, CONSENTED), None])
    failed = set()
    export_entries([("1-0", _fields(sid, 0))], lambda _sid: next(answers), KEY, tmp_path,
                   failed_deletions=failed)
    assert failed == {uid} and user_dir(tmp_path, uid).exists()
    retry_deletions(failed, tmp_path)
    assert failed == {uid}
    monkeypatch.setattr(files, "_rmtree", shutil.rmtree)  # lock released
    retry_deletions(failed, tmp_path)
    assert failed == set() and not user_dir(tmp_path, uid).exists()
