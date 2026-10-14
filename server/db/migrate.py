"""Plain SQL migration runner.

Usage::

    .venv/Scripts/python -m server.db.migrate [--env-file .env]

Applies every ``server/*/migrations/NNNN_<name>.sql`` file in global filename
order. Each file runs in its own transaction and is recorded in
``schema_migrations`` with a SHA-256 checksum, so running the command again
applies nothing. A file that changes after it was applied is refused. See
``server/db/README.md`` for the numbering convention.
"""

from __future__ import annotations

from server.common.production import require_production_ready

import argparse
import hashlib
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import psycopg

from server.common.config import load_env_file

SERVER_ROOT = Path(__file__).resolve().parents[1]
FILENAME_RE = re.compile(r"^\d{4}_[a-z0-9_]+\.sql$")
LOCK_ID = 7_403_771  # advisory lock so two runners never interleave

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename   text PRIMARY KEY,
    folder     text NOT NULL,
    checksum   text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
)
"""


class MigrationError(Exception):
    """A migration could not be discovered or applied."""


@dataclass(frozen=True)
class Migration:
    filename: str
    folder: str
    path: Path

    def sql(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def checksum(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


def discover(root: Path = SERVER_ROOT) -> list[Migration]:
    found: dict[str, Migration] = {}
    for path in sorted(Path(root).glob("*/migrations/*.sql")):
        if not FILENAME_RE.match(path.name):
            raise MigrationError(f"{path}: migration files must be named NNNN_<name>.sql")
        folder = path.parent.parent.name
        if path.name in found:
            raise MigrationError(
                f"duplicate migration filename {path.name} in {found[path.name].folder} and {folder}"
            )
        found[path.name] = Migration(path.name, folder, path)
    return [found[name] for name in sorted(found)]


def apply_migrations(conninfo: str, root: Path = SERVER_ROOT) -> list[str]:
    """Apply pending migrations and return the filenames applied, in order."""
    migrations = discover(root)
    applied_now: list[str] = []
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))
        try:
            conn.execute(CREATE_TABLE)
            done = dict(conn.execute("SELECT filename, checksum FROM schema_migrations").fetchall())
            for migration in migrations:
                checksum = migration.checksum()
                if migration.filename in done:
                    if done[migration.filename] != checksum:
                        raise MigrationError(
                            f"{migration.filename} changed after it was applied; "
                            "add a new migration instead"
                        )
                    continue
                try:
                    with conn.transaction():
                        conn.execute(migration.sql())
                        conn.execute(
                            "INSERT INTO schema_migrations (filename, folder, checksum) "
                            "VALUES (%s, %s, %s)",
                            (migration.filename, migration.folder, checksum),
                        )
                except psycopg.Error as exc:
                    raise MigrationError(f"{migration.filename} failed: {exc}") from exc
                applied_now.append(migration.filename)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))
    return applied_now


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply AuthWho SQL migrations.")
    parser.add_argument("--env-file", help="read missing variables from this file, for example .env")
    args = parser.parse_args(argv)
    if args.env_file:
        load_env_file(args.env_file)
    require_production_ready()
    url = os.environ.get("AUTHWHO_DATABASE_URL")
    if not url:
        print("AUTHWHO_DATABASE_URL is not set", file=sys.stderr)
        return 2
    try:
        applied = apply_migrations(url)
    except MigrationError as exc:
        print(f"migration failed: {exc}", file=sys.stderr)
        return 1
    print(f"applied {len(applied)} migration(s)" + (": " + ", ".join(applied) if applied else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
