"""C10 (format): encrypted, length-prefixed research files and their reader."""

import os
import shutil
import uuid

import pytest

from server.common.crypto import CryptoError
from server.research.files import append_batch, read_session_file, session_file

KEY = os.urandom(32)
UID = str(uuid.uuid4())
SID = str(uuid.uuid4())


def _batch(seq):
    return {"session_id": SID, "stream_id": str(uuid.uuid4()), "seq": seq,
            "received_at": "2026-10-09T12:00:00.000Z", "pointer_device": "mouse",
            "events": [[1, 1201.3, 1, seq], [2, 1288.9, 1, seq]]}


def test_round_trip_of_several_batches(tmp_path):
    batches = [_batch(0), _batch(1), _batch(2)]
    for b in batches:
        append_batch(tmp_path, UID, b, KEY)
    path = session_file(tmp_path, UID, SID)
    assert path.parent.name == UID and path.name == f"{SID}.bin"
    assert read_session_file(path, KEY) == batches


def test_ciphertext_contains_no_plaintext_event_json(tmp_path):
    append_batch(tmp_path, UID, _batch(0), KEY)
    data = session_file(tmp_path, UID, SID).read_bytes()
    for needle in (b"events", b"1201.3", b"[[1,", b"[1, 1201", b"pointer_device", SID.encode()):
        assert needle not in data


def test_wrong_key_fails(tmp_path):
    append_batch(tmp_path, UID, _batch(0), KEY)
    with pytest.raises(CryptoError):
        read_session_file(session_file(tmp_path, UID, SID), os.urandom(32))


def test_file_copied_to_another_session_name_fails(tmp_path):
    append_batch(tmp_path, UID, _batch(0), KEY)
    src = session_file(tmp_path, UID, SID)
    dst = src.with_name(f"{uuid.uuid4()}.bin")
    shutil.copy(src, dst)
    with pytest.raises(CryptoError):
        read_session_file(dst, KEY)


def test_truncated_file_is_reported(tmp_path):
    append_batch(tmp_path, UID, _batch(0), KEY)
    path = session_file(tmp_path, UID, SID)
    path.write_bytes(path.read_bytes()[:-5])
    with pytest.raises(CryptoError):
        read_session_file(path, KEY)


# ---- verified deletion ---------------------------------------------------------------------

import sys  # noqa: E402

from server.research import files  # noqa: E402
from server.research.files import DeletionIncomplete, delete_user_folder, user_dir  # noqa: E402


@pytest.fixture
def fast_retries(monkeypatch):
    monkeypatch.setattr(files, "RETRY_DELAY_S", 0)


def test_delete_removes_folder_and_missing_folder_is_fine(tmp_path):
    append_batch(tmp_path, UID, _batch(0), KEY)
    delete_user_folder(tmp_path, UID)
    assert not user_dir(tmp_path, UID).exists()
    delete_user_folder(tmp_path, UID)


def test_delete_retries_after_a_transient_lock(tmp_path, monkeypatch, fast_retries):
    append_batch(tmp_path, UID, _batch(0), KEY)
    calls = []

    def flaky(path):
        calls.append(path)
        if len(calls) < 3:
            raise PermissionError("locked")
        shutil.rmtree(path)

    monkeypatch.setattr(files, "_rmtree", flaky)
    delete_user_folder(tmp_path, UID)
    assert len(calls) == 3 and not user_dir(tmp_path, UID).exists()


def test_delete_fails_loudly_when_folder_survives(tmp_path, monkeypatch, fast_retries):
    append_batch(tmp_path, UID, _batch(0), KEY)
    monkeypatch.setattr(files, "_rmtree", lambda path: None)  # reports success, deletes nothing
    with pytest.raises(DeletionIncomplete):
        delete_user_folder(tmp_path, UID)
    assert user_dir(tmp_path, UID).exists()


@pytest.mark.skipif(sys.platform != "win32", reason="open files block deletion only on Windows")
def test_delete_fails_while_windows_holds_a_file_open(tmp_path, fast_retries):
    path = append_batch(tmp_path, UID, _batch(0), KEY)
    with open(path, "rb"):
        with pytest.raises(DeletionIncomplete):
            delete_user_folder(tmp_path, UID)
    delete_user_folder(tmp_path, UID)
    assert not user_dir(tmp_path, UID).exists()
