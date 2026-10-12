"""Retention jobs (proposal Section 9; docs/interfaces.md sections 7 to 12).

Usage::

    .venv/Scripts/python -m server.db.retention [--env-file .env]

One function per rule. PostgreSQL rules take ``(conn, now=None)`` and return
the number of rows deleted; ``run_rule`` runs each in its own transaction with
``authwho.retention = on`` (the append-only decision log only allows deletes
under that setting). Later phases add their rules to ``DB_RULES``:
trust points (30 days) and decisions (90 days).
Only counts are printed, never row contents.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import psycopg
import redis

from server.common.config import load_env_file
from server.common.redis_keys import EVENTS_STREAM, raw_event_min_id

SESSION_RETENTION = timedelta(days=90)
WINDOW_RETENTION = timedelta(days=30)
TRUST_POINT_RETENTION = timedelta(days=30)  # ruling R7
DECISION_RETENTION = timedelta(days=90)

DbRule = Callable[..., int]


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def delete_expired_sessions(conn: psycopg.Connection, now: datetime | None = None) -> int:
    cur = conn.execute(
        "DELETE FROM sessions WHERE created_at < %s", (_now(now) - SESSION_RETENTION,)
    )
    return cur.rowcount


def delete_expired_windows(conn: psycopg.Connection, now: datetime | None = None) -> int:
    cur = conn.execute(
        "DELETE FROM windows WHERE created_at < %s", (_now(now) - WINDOW_RETENTION,)
    )
    return cur.rowcount


def delete_expired_trust_points(conn: psycopg.Connection, now: datetime | None = None) -> int:
    cur = conn.execute(
        "DELETE FROM trust_points WHERE created_at < %s", (_now(now) - TRUST_POINT_RETENTION,)
    )
    return cur.rowcount


def delete_expired_decisions(conn: psycopg.Connection, now: datetime | None = None) -> int:
    """The only permitted delete on the append-only decisions table."""
    conn.execute("SELECT set_config('authwho.retention', 'on', true)")
    cur = conn.execute(
        "DELETE FROM decisions WHERE created_at < %s", (_now(now) - DECISION_RETENTION,)
    )
    conn.execute("SELECT set_config('authwho.retention', 'off', true)")
    return cur.rowcount


def trim_raw_events(client: redis.Redis, now_ms: int | None = None) -> int:
    """Remove raw event batches older than 24 hours, even if no new batch arrives."""
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    return int(client.xtrim(EVENTS_STREAM, minid=raw_event_min_id(now_ms), approximate=False))


DB_RULES: list[DbRule] = [delete_expired_sessions, delete_expired_windows, delete_expired_trust_points,
                          delete_expired_decisions]


def run_rule(conn: psycopg.Connection, rule: DbRule, now: datetime | None = None) -> int:
    with conn.transaction():
        conn.execute("SET LOCAL authwho.retention = 'on'")
        return rule(conn, now=now)


def run_all(conn: psycopg.Connection, client: redis.Redis, now: datetime | None = None) -> dict[str, int]:
    counts = {rule.__name__: run_rule(conn, rule, now) for rule in DB_RULES}
    counts["trim_raw_events"] = trim_raw_events(client)
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply AuthWho retention rules.")
    parser.add_argument("--env-file", help="read missing variables from this file, for example .env")
    args = parser.parse_args(argv)
    if args.env_file:
        load_env_file(args.env_file)
    db_url = os.environ.get("AUTHWHO_DATABASE_URL")
    redis_url = os.environ.get("AUTHWHO_REDIS_URL")
    if not db_url or not redis_url:
        print("AUTHWHO_DATABASE_URL and AUTHWHO_REDIS_URL must be set", file=sys.stderr)
        return 2
    client = redis.Redis.from_url(redis_url)
    try:
        with psycopg.connect(db_url, autocommit=True) as conn:
            counts = run_all(conn, client)
    finally:
        client.close()
    for name, count in counts.items():
        print(f"{name}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
