"""Volunteer research files (docs/interfaces.md section 12).

Layout: ``data/volunteer/<user_id>/<session_id>.bin``. A file is a sequence
of records, each a 4-byte big-endian length followed by an AES-256-GCM blob
(``server.common.crypto``) encrypted with ``RESEARCH_EXPORT_KEY``. The
plaintext of a record is the JSON of one raw batch as stored in ``aw:events``
(events decoded to a list). The session id is bound as associated data, so a
record moved to another session's file fails to decrypt.
"""

from __future__ import annotations

import json
import shutil
import struct
import time
import uuid
from pathlib import Path

from server.common.crypto import CryptoError, decrypt, encrypt

_LEN = struct.Struct(">I")

# Deletion is verified and retried, because on Windows (and in OneDrive
# folders) an open handle can keep a file alive after rmtree reports an error.
RETRY_ATTEMPTS = 5
RETRY_DELAY_S = 0.2
_rmtree = shutil.rmtree


class DeletionIncomplete(Exception):
    """A user's research folder still exists after every deletion attempt."""

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESEARCH_DIR = REPO_ROOT / "data" / "volunteer"


def user_dir(base: Path, user_id: str) -> Path:
    # Only canonical UUIDs become folder names, so no path can escape ``base``.
    return Path(base) / str(uuid.UUID(user_id))


def session_file(base: Path, user_id: str, session_id: str) -> Path:
    return user_dir(base, user_id) / f"{uuid.UUID(session_id)}.bin"


def delete_user_folder(base: Path, user_id: str) -> None:
    """Delete the folder and confirm it is gone, or raise ``DeletionIncomplete``."""
    path = user_dir(base, user_id)
    for attempt in range(RETRY_ATTEMPTS):
        if not path.exists():
            return
        try:
            _rmtree(path)
        except FileNotFoundError:
            pass
        except OSError:
            pass  # a lock; checked and retried below
        if not path.exists():
            return
        if attempt < RETRY_ATTEMPTS - 1:
            time.sleep(RETRY_DELAY_S)
    raise DeletionIncomplete("research folder could not be deleted")


def _aad(session_id: str) -> bytes:
    return b"authwho-research-v1:" + str(uuid.UUID(session_id)).encode()


def append_batch(base: Path, user_id: str, batch: dict, key: bytes) -> Path:
    """Encrypt one raw batch and append it to the session's file."""
    path = session_file(base, user_id, batch["session_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = encrypt(json.dumps(batch, separators=(",", ":")).encode(), key,
                   aad=_aad(batch["session_id"]))
    with open(path, "ab") as fh:
        fh.write(_LEN.pack(len(blob)) + blob)
    return path


def read_session_file(path: Path, key: bytes) -> list[dict]:
    """Decrypt every record of one session file (for ml dataset loaders)."""
    path = Path(path)
    aad = _aad(path.stem)
    data = path.read_bytes()
    batches, pos = [], 0
    while pos < len(data):
        if pos + _LEN.size > len(data):
            raise CryptoError("truncated record header")
        (length,) = _LEN.unpack_from(data, pos)
        pos += _LEN.size
        if pos + length > len(data):
            raise CryptoError("truncated record")
        batches.append(json.loads(decrypt(data[pos:pos + length], key, aad=aad)))
        pos += length
    return batches
