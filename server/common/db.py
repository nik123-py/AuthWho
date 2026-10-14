"""Reusable PostgreSQL connections.

``Connector(conninfo)()`` is a context manager that yields a connection kept open
for the calling thread, commits when the block succeeds, rolls back when it
raises, and reconnects if the connection was closed or broken. It replaces
opening a new connection for every query, which dominated the worker's time.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from collections.abc import Iterator

import psycopg


class Connector:
    def __init__(self, conninfo: str, **kwargs) -> None:
        self.conninfo = conninfo
        self.kwargs = kwargs
        self._local = threading.local()

    def _get(self) -> psycopg.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None or conn.closed or conn.broken:
            conn = psycopg.connect(self.conninfo, **self.kwargs)
            self._local.conn = conn
        return conn

    @contextmanager
    def __call__(self) -> Iterator[psycopg.Connection]:
        conn = self._get()
        try:
            yield conn
            conn.commit()
        except BaseException:
            try:
                conn.rollback()
            except psycopg.Error:
                self._local.conn = None
            raise

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
