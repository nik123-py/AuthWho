"""Feature pipeline: raw batches to encrypted kf-1 windows, honouring opt-outs."""

import json
import os
import uuid

import pytest

from server.common.crypto import CryptoError
from server.features.keystroke import extract_keystroke
from server.features.types import KeyPress
from server.worker.pipeline import FeaturePipeline
from server.worker.store import UserContext, decrypt_features

KEY = os.urandom(32)


class FakeStore:
    def __init__(self, contexts):
        self.contexts = contexts
        self.rows = []
        self.refuse = False

    def user_context(self, session_id):
        return self.contexts.get(session_id)

    def insert_window(self, rec):
        if self.refuse:
            return False
        self.rows.append(rec)
        return True


def _presses(start, n):
    events = []
    for k in range(start, start + n):
        events += [[1, k * 100.0, 1, k], [2, k * 100.0 + 60.0 + (k % 3), 1, k]]
    return events


def _entry(session_id, stream_id, seq, events, device="mouse"):
    return (f"{seq + 1}-0", {"session_id": session_id, "stream_id": stream_id, "seq": str(seq),
                             "received_at": "2026-10-12T12:00:00.000Z",
                             "pointer_device": device, "events": json.dumps(events)})


@pytest.fixture
def ids():
    return str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())  # user, session, stream


def test_batches_become_encrypted_windows(ids):
    user, session, stream = ids
    store = FakeStore({session: UserContext(user, (), False)})
    pipe = FeaturePipeline(store, KEY)
    entries = [_entry(session, stream, s, _presses(s * 25, 25)) for s in range(4)]
    assert pipe.process(entries) == 3
    assert len(store.rows) == 3
    rec = store.rows[0]
    assert (rec.session_id, rec.stream_id, rec.user_id) == (session, stream, user)
    assert (rec.channel, rec.schema, rec.pointer_device) == ("keystroke", "kf-1", "mouse")
    assert rec.n_actions == 50
    assert rec.start_t == 0.0 and rec.end_t == 4900.0 + 60.0 + (49 % 3)
    expected = extract_keystroke(
        [KeyPress(1, k * 100.0, k * 100.0 + 60.0 + (k % 3)) for k in range(50)])
    assert decrypt_features(rec.features_enc, KEY, rec.window_id) == expected.values
    assert rec.quality == pytest.approx(expected.quality)
    assert b"dwell" not in rec.features_enc and b"[" not in rec.features_enc[:2]


def test_ciphertext_is_bound_to_its_window_id(ids):
    user, session, stream = ids
    store = FakeStore({session: UserContext(user, (), False)})
    FeaturePipeline(store, KEY).process([_entry(session, stream, 0, _presses(0, 50))])
    rec = store.rows[0]
    with pytest.raises(CryptoError):
        decrypt_features(rec.features_enc, KEY, str(uuid.uuid4()))


@pytest.mark.parametrize("ctx", [
    UserContext("u", ("keystroke",), False),
    UserContext("u", (), True),
    None,
])
def test_opted_out_exempt_or_unknown_users_get_no_windows(ids, ctx):
    _user, session, stream = ids
    store = FakeStore({session: ctx} if ctx else {})
    assert FeaturePipeline(store, KEY).process([_entry(session, stream, 0, _presses(0, 60))]) == 0
    assert store.rows == []


def test_streams_are_windowed_separately(ids):
    user, session, _ = ids
    store = FakeStore({session: UserContext(user, (), False)})
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    pipe = FeaturePipeline(store, KEY)
    assert pipe.process([_entry(session, a, 0, _presses(0, 30)), _entry(session, b, 0, _presses(0, 30))]) == 0


def test_malformed_entries_are_skipped(ids):
    user, session, stream = ids
    store = FakeStore({session: UserContext(user, (), False)})
    bad = ("1-0", {"session_id": session, "stream_id": stream, "events": "not json"})
    empty = ("2-0", {})
    short = _entry(session, str(uuid.uuid4()), 0, [[1, 0.0]])
    entries = [bad, empty, short, _entry(session, stream, 0, _presses(0, 50))]
    assert FeaturePipeline(store, KEY).process(entries) == 1


def test_unknown_pointer_device_is_stored_as_unknown(ids):
    user, session, stream = ids
    store = FakeStore({session: UserContext(user, (), False)})
    FeaturePipeline(store, KEY).process([_entry(session, stream, 0, _presses(0, 50), device="pen")])
    assert store.rows[0].pointer_device == "unknown"


def test_refused_insert_is_not_counted(ids):
    user, session, stream = ids
    store = FakeStore({session: UserContext(user, (), False)})
    store.refuse = True
    assert FeaturePipeline(store, KEY).process([_entry(session, stream, 0, _presses(0, 50))]) == 0


def test_idle_streams_are_evicted(ids):
    user, session, stream = ids
    now = [0.0]
    store = FakeStore({session: UserContext(user, (), False)})
    pipe = FeaturePipeline(store, KEY, idle_s=60, clock=lambda: now[0])
    pipe.process([_entry(session, stream, 0, _presses(0, 30))])
    assert pipe.open_streams() == 1
    now[0] = 61.0
    pipe.process([])
    assert pipe.open_streams() == 0
