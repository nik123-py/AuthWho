"""Pytest fixtures shared by integration tests. Test-only code.

Integration tests never touch development data: PostgreSQL tests use a
separate database named ``<dbname>_test`` and Redis tests use logical
database 15. Configuration comes from the environment (as in CI) or, when a
variable is missing, from the repository ``.env`` file.

Several pytest runs may start at once on one laptop (for example two agents).
The fixtures hold a lock for the whole run, so a second run waits instead of
flushing or rebuilding the shared test databases mid-test. The lock is a key in
Redis database 14 with a short TTL renewed by a heartbeat thread, so a run that
is killed releases it within seconds. (A PostgreSQL advisory lock was tried
first; it stayed held forever because the Docker Desktop port proxy keeps a
killed client's connection open on the server side.)

Import the fixtures in a ``tests/conftest.py``::

    from server.common.testing import pg_conn, pg_url, redis_client  # noqa: F401
"""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
import time
import uuid
from pathlib import Path

import psycopg
import pytest
import redis
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from server.common.config import load_env_file

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_REDIS_DB = 15
LOCK_REDIS_DB = 14  # never flushed by any fixture
LOCK_KEY = "authwho:test:integration-lock"
LOCK_TTL_MS = 30_000
LOCK_HEARTBEAT_S = 10
LOCK_WAIT_S = 900

_RENEW = "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('PEXPIRE', KEYS[1], ARGV[2]) end return 0"
_RELEASE = "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end return 0"


def integration_env() -> dict[str, str]:
    env = dict(os.environ)
    dotenv = REPO_ROOT / ".env"
    if dotenv.exists():
        load_env_file(dotenv, env)
    return env


def database_url_for_tests(env: dict[str, str] | None = None) -> str:
    env = env or integration_env()
    base = env.get("AUTHWHO_DATABASE_URL")
    if not base:
        raise RuntimeError("AUTHWHO_DATABASE_URL is not set for integration tests")
    params = conninfo_to_dict(base)
    params["dbname"] = f"{params.get('dbname', 'authwho')}_test"
    return make_conninfo(**params)


def lock_redis_url(env: dict[str, str] | None = None) -> str:
    return redis_url_for_tests(env, db=LOCK_REDIS_DB)


def acquire_lock(client: redis.Redis, key: str, token: str, ttl_ms: int = LOCK_TTL_MS,
                 wait_s: float = LOCK_WAIT_S) -> bool:
    deadline = time.monotonic() + wait_s
    while not client.set(key, token, nx=True, px=ttl_ms):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.2)
    return True


def release_lock(client: redis.Redis, key: str, token: str) -> None:
    client.eval(_RELEASE, 1, key, token)


def redis_url_for_tests(env: dict[str, str] | None = None, db: int = TEST_REDIS_DB) -> str:
    env = env or integration_env()
    base = env.get("AUTHWHO_REDIS_URL", "redis://localhost:6379/0")
    client = redis.Redis.from_url(base)
    kwargs = client.connection_pool.connection_kwargs
    client.close()
    auth = ""
    if kwargs.get("password"):
        auth = f"{kwargs.get('username') or ''}:{kwargs['password']}@"
    return f"redis://{auth}{kwargs.get('host', 'localhost')}:{kwargs.get('port', 6379)}/{db}"


def _ensure_database(url: str) -> None:
    params = conninfo_to_dict(url)
    name = params["dbname"]
    admin = make_conninfo(**dict(params, dbname="postgres"))
    with psycopg.connect(admin, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))


def user_tables(conn: psycopg.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
        "AND table_name <> 'schema_migrations' ORDER BY table_name"
    ).fetchall()
    return [r[0] for r in rows]


_holders = 0
_holders_guard = threading.Lock()


@contextmanager
def integration_lock_held():
    """Hold the cross-run lock. Re-entrant within one process: pytest creates one
    session fixture per conftest that imports it, and those must share the lock."""
    global _holders
    with _holders_guard:
        if _holders:
            _holders += 1
            nested = True
        else:
            nested = False
    if nested:
        try:
            yield
        finally:
            with _holders_guard:
                _holders -= 1
        return

    client = redis.Redis.from_url(lock_redis_url(), decode_responses=True)
    token = str(uuid.uuid4())
    if not acquire_lock(client, LOCK_KEY, token, wait_s=LOCK_WAIT_S):
        client.close()
        pytest.fail("another pytest run held the integration lock for too long")
    stop = threading.Event()

    def heartbeat():
        while not stop.wait(LOCK_HEARTBEAT_S):
            try:
                client.eval(_RENEW, 1, LOCK_KEY, token, LOCK_TTL_MS)
            except redis.RedisError:
                pass

    thread = threading.Thread(target=heartbeat, name="integration-lock", daemon=True)
    thread.start()
    with _holders_guard:
        _holders += 1
    try:
        yield
    finally:
        with _holders_guard:
            _holders -= 1
        stop.set()
        thread.join(timeout=5)
        release_lock(client, LOCK_KEY, token)
        client.close()


@pytest.fixture(scope="session")
def integration_lock():
    """Hold the cross-run lock for the whole pytest session."""
    with integration_lock_held():
        yield


@pytest.fixture(scope="session")
def pg_url(integration_lock) -> str:
    """A freshly migrated test database (schema rebuilt once per test run)."""
    from server.db.migrate import apply_migrations

    url = database_url_for_tests()
    _ensure_database(url)
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")
    apply_migrations(url)
    return url


@pytest.fixture
def pg_conn(pg_url):
    """An autocommit connection to the test database with every data table emptied."""
    with psycopg.connect(pg_url, autocommit=True) as conn:
        tables = user_tables(conn)
        if tables:
            conn.execute(
                sql.SQL("TRUNCATE {} CASCADE").format(
                    sql.SQL(", ").join(sql.Identifier(t) for t in tables)
                )
            )
        yield conn


@pytest.fixture
def redis_client(integration_lock):
    """A client for the test Redis database, flushed before and after each test."""
    client = redis.Redis.from_url(redis_url_for_tests(), decode_responses=True)
    client.flushdb()
    yield client
    client.flushdb()
    client.close()
