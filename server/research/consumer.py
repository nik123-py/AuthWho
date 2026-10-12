"""Volunteer research export consumer (docs/interfaces.md section 12).

Usage::

    .venv/Scripts/python -m server.research [--env-file .env] [--once]

Reads ``aw:events`` with its own consumer group ``research``. For users with
``research_consent = true`` only, each raw batch is appended, encrypted with
``RESEARCH_EXPORT_KEY``, to ``data/volunteer/<user_id>/<session_id>.bin``.
A batch is exported only if its ``received_at`` is at or after
``research_consent_at``, so batches captured before research consent are never
exported, even when the consumer was down at the time. Every entry is
acknowledged whether or not it was exported. Consent is looked
up for each batch so a withdrawal takes effect at once; it is checked again
after writing, and the user's folder is removed if consent disappeared in
between. Only counts are logged, never batch contents.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import psycopg
import redis

from server.common.config import ConfigError, load_env_file, load_settings
from server.common.redis_keys import EVENTS_STREAM
from server.research.files import (
    DEFAULT_RESEARCH_DIR,
    DeletionIncomplete,
    append_batch,
    delete_user_folder,
)

GROUP = "research"
CONSUMER = "research-1"
BLOCK_MS = 5000

log = logging.getLogger("authwho.research")

# session_id -> (user_id, research_consent_at or None), or None for an unknown session.
ConsentLookup = Callable[[str], "tuple[str, datetime | None] | None"]


def entry_to_batch(fields: dict) -> dict:
    return {
        "session_id": fields["session_id"],
        "stream_id": fields["stream_id"],
        "seq": int(fields["seq"]),
        "received_at": fields["received_at"],
        "pointer_device": fields["pointer_device"],
        "events": json.loads(fields["events"]),
    }


def _received_at(fields: dict) -> datetime | None:
    try:
        value = datetime.fromisoformat(fields.get("received_at", ""))
    except (TypeError, ValueError):
        return None
    return value if value.tzinfo is not None else None


def _consented_user(lookup: ConsentLookup, session_id: str, received_at: datetime) -> str | None:
    """The user id if research consent was in force when the batch was received."""
    found = lookup(session_id)
    if found is None:
        return None
    user_id, consent_at = found
    if consent_at is None or received_at < consent_at:
        return None
    return user_id


def _delete_or_remember(base_dir: Path, user_id: str, failed: set[str] | None) -> None:
    try:
        delete_user_folder(base_dir, user_id)
    except DeletionIncomplete:
        log.error("research folder deletion incomplete; will retry")
        if failed is not None:
            failed.add(user_id)


def retry_deletions(failed: set[str], base_dir: Path) -> None:
    """Retry folder deletions that failed earlier (for example a Windows file lock)."""
    for user_id in list(failed):
        try:
            delete_user_folder(base_dir, user_id)
        except DeletionIncomplete:
            continue
        failed.discard(user_id)


def export_entries(entries: list[tuple[str, dict]], lookup: ConsentLookup, key: bytes,
                   base_dir: Path, failed_deletions: set[str] | None = None) -> int:
    written = 0
    for _entry_id, fields in entries:
        session_id = fields.get("session_id", "")
        received_at = _received_at(fields)
        if received_at is None:
            continue
        user_id = _consented_user(lookup, session_id, received_at)
        if user_id is None:
            continue
        append_batch(base_dir, user_id, entry_to_batch(fields), key)
        if _consented_user(lookup, session_id, received_at) != user_id:
            _delete_or_remember(base_dir, user_id, failed_deletions)
            continue
        written += 1
    return written


def ensure_group(client: redis.Redis) -> None:
    try:
        client.xgroup_create(EVENTS_STREAM, GROUP, id="0", mkstream=True)
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def run_once(client: redis.Redis, lookup: ConsentLookup, key: bytes, base_dir: Path,
             block_ms: int | None = None, count: int = 100,
             failed_deletions: set[str] | None = None) -> int:
    """Process this consumer's pending entries, then new ones. Returns batches written."""
    if failed_deletions:
        retry_deletions(failed_deletions, base_dir)
    ensure_group(client)
    written = 0
    for start, block in (("0", None), (">", block_ms)):
        while True:
            reply = client.xreadgroup(GROUP, CONSUMER, {EVENTS_STREAM: start}, count=count,
                                      block=block)
            entries = reply[0][1] if reply else []
            entries = [(i, f) for i, f in entries if f]  # trimmed entries come back empty
            acked = [i for i, _ in (reply[0][1] if reply else [])]
            if not acked:
                break
            written += export_entries(entries, lookup, key, base_dir, failed_deletions)
            client.xack(EVENTS_STREAM, GROUP, *acked)
            if start == ">":
                break
    return written


def make_client(url: str) -> redis.Redis:
    """Redis client whose read timeout outlasts a blocking XREADGROUP.

    redis-py 8 otherwise times out socket reads after 5 seconds.
    """
    return redis.Redis.from_url(url, decode_responses=True,
                                socket_timeout=BLOCK_MS / 1000 + 10)


def pg_consent_lookup(conninfo: str) -> ConsentLookup:
    def lookup(session_id: str) -> tuple[str, datetime | None] | None:
        with psycopg.connect(conninfo, autocommit=True) as conn:
            row = conn.execute(
                "SELECT u.user_id, u.research_consent_at FROM sessions s "
                "JOIN users u ON u.user_id = s.user_id WHERE s.session_id = %s",
                (session_id,),
            ).fetchone()
        return (str(row[0]), row[1]) if row else None

    return lookup


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export research-consented raw batches.")
    parser.add_argument("--env-file", help="read missing variables from this file, for example .env")
    parser.add_argument("--once", action="store_true", help="process what is waiting, then exit")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    if args.env_file:
        load_env_file(args.env_file)
    try:
        settings = load_settings()
        key = settings.require("research_export_key")
        client = make_client(settings.require("redis_url"))
        lookup = pg_consent_lookup(settings.require("database_url"))
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    failed: set[str] = set()
    try:
        while True:
            written = run_once(client, lookup, key, DEFAULT_RESEARCH_DIR, block_ms=BLOCK_MS,
                               failed_deletions=failed)
            if written:
                log.info("exported %d batch(es)", written)
            if args.once:
                return 0
    except KeyboardInterrupt:
        return 0
    finally:
        client.close()
