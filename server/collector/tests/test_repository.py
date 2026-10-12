"""Contract tests run against both repositories (memory and PostgreSQL)."""

import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from server.collector.repository import MemoryRepository, PostgresRepository, UserRecord


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.integration)])
def repo(request):
    if request.param == "memory":
        return MemoryRepository()
    request.getfixturevalue("pg_conn")  # empties the tables
    return PostgresRepository(request.getfixturevalue("pg_url"))


def _user(**overrides):
    values = dict(
        user_id=str(uuid.uuid4()), app_id="demo", role="analyst", consent_version="1",
        consent_at=datetime(2026, 10, 9, 10, 0, tzinfo=timezone.utc), research_consent=False,
        opt_outs=["interaction"], exempt=False, pointer_device="touchpad",
    )
    values.update(overrides)
    return UserRecord(**values)


def test_upsert_creates_then_updates_and_returns_previous(repo):
    user = _user()
    assert repo.upsert_user(user) is None
    assert repo.get_user(user.user_id) == user
    changed = _user(user_id=user.user_id, research_consent=True, opt_outs=[])
    previous = repo.upsert_user(changed, now=T1)
    assert previous == user
    assert repo.get_user(user.user_id) == replace(changed, research_consent_at=T1)


def test_upsert_keeps_exemption_set_elsewhere(repo):
    user = _user()
    repo.upsert_user(user)
    repo.set_exempt(user.user_id, True)
    repo.upsert_user(_user(user_id=user.user_id, consent_version="2"))
    stored = repo.get_user(user.user_id)
    assert stored.exempt is True and stored.consent_version == "2"


def test_sessions_are_created_and_read(repo):
    user = _user()
    repo.upsert_user(user)
    sid = str(uuid.uuid4())
    repo.create_session(sid, user.user_id, "demo", "analyst")
    session = repo.get_session(sid)
    assert (session.session_id, session.user_id, session.status) == (sid, user.user_id, "active")
    assert session.ended_at is None
    assert repo.get_session(str(uuid.uuid4())) is None


def test_delete_user_removes_row_ends_sessions_and_returns_their_ids(repo):
    user, other = _user(), _user()
    repo.upsert_user(user)
    repo.upsert_user(other)
    mine = [str(uuid.uuid4()), str(uuid.uuid4())]
    for sid in mine:
        repo.create_session(sid, user.user_id, "demo", "analyst")
    theirs = str(uuid.uuid4())
    repo.create_session(theirs, other.user_id, "demo", "analyst")
    assert sorted(repo.delete_user(user.user_id)) == sorted(mine)
    assert repo.get_user(user.user_id) is None
    assert all(repo.get_session(s).status == "terminated" for s in mine)
    assert all(repo.get_session(s).ended_at is not None for s in mine)
    assert repo.get_session(theirs).status == "active"
    assert repo.get_user(other.user_id) is not None
    # Deleting again is harmless and still reports the user's sessions for clean-up.
    assert sorted(repo.delete_user(user.user_id)) == sorted(mine)


def test_end_session_marks_it_terminated_once(repo):
    user = _user()
    repo.upsert_user(user)
    sid, other = str(uuid.uuid4()), str(uuid.uuid4())
    repo.create_session(sid, user.user_id, "demo", "analyst")
    repo.create_session(other, user.user_id, "demo", "analyst")
    assert repo.end_session(sid) is True
    ended = repo.get_session(sid)
    assert ended.status == "terminated" and ended.ended_at is not None
    assert repo.end_session(sid) is True
    assert repo.get_session(sid).ended_at == ended.ended_at
    assert repo.get_session(other).status == "active"
    assert repo.end_session(str(uuid.uuid4())) is False


T1 = datetime(2026, 10, 9, 12, 0, 0, 123000, tzinfo=timezone.utc)


def test_research_consent_at_follows_consent_transitions(repo):
    t2, t3 = T1 + timedelta(minutes=5), T1 + timedelta(minutes=10)
    user = _user(research_consent=True)
    repo.upsert_user(user, now=T1)
    assert repo.get_user(user.user_id).research_consent_at == T1  # new user with consent
    repo.upsert_user(replace(user, consent_version="2"), now=t2)
    assert repo.get_user(user.user_id).research_consent_at == T1  # still consenting: unchanged
    repo.upsert_user(replace(user, research_consent=False), now=t2)
    assert repo.get_user(user.user_id).research_consent_at is None  # withdrawn: cleared
    repo.upsert_user(user, now=t3)
    assert repo.get_user(user.user_id).research_consent_at == t3  # given again: new time
    other = _user(research_consent=False)
    repo.upsert_user(other, now=T1)
    assert repo.get_user(other.user_id).research_consent_at is None
