"""Hot state for streams, nonces, rate limits and the raw event stream.

``RedisHotStore`` is the production store (docs/interfaces.md section 7). The
sequence, nonce, session-status checks and the ``XADD`` run in one Lua script,
so a batch is either fully accepted and stored or not at all.
``MemoryHotStore`` has the same behaviour for unit tests; both pass the same
contract tests in ``tests/test_hot_store.py``.

Every ``XADD`` trims ``aw:events`` with an exact ``MINID`` of now minus 24 hours.
Exact rather than approximate (``~``) trimming is used because ``~`` only drops
whole internal nodes and can leave entries older than 24 hours in place.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime

import redis

from server.common.redis_keys import (
    EVENTS_STREAM,
    RAW_EVENT_RETENTION_MS,
    SESSION_TTL_S,
    nonce_key,
    rate_key,
    session_key,
    stream_key,
)

DEFAULT_RATE_PER_S = 5.0
DEFAULT_BURST = 20


@dataclass(frozen=True)
class StreamRecord:
    stream_id: str
    session_id: str
    user_id: str
    stream_key: str
    channels: dict[str, bool]
    pointer_device: str
    expires_at: datetime


def _rate_ttl_ms(rate: float, burst: int) -> int:
    return int(math.ceil(burst / rate * 1000)) + 1000


class MemoryHotStore:
    """In-process store with the same semantics as ``RedisHotStore``. Tests only."""

    def __init__(self, rate_per_s: float = DEFAULT_RATE_PER_S, burst: int = DEFAULT_BURST,
                 clock: Callable[[], float] = time.monotonic):
        self.rate, self.burst, self.clock = float(rate_per_s), burst, clock
        self.streams: dict[str, StreamRecord] = {}
        self.last_seq: dict[str, int] = {}
        self.nonces: dict[str, set[str]] = {}
        self.buckets: dict[str, tuple[float, float]] = {}
        self.sessions: dict[str, str] = {}
        self.events: list[tuple[str, dict[str, str]]] = []
        self._counter = 0

    def create_session_state(self, session_id: str) -> None:
        self.sessions[session_id] = "active"

    def session_status(self, session_id: str) -> str | None:
        return self.sessions.get(session_id)

    def set_session_status(self, session_id: str, status: str) -> None:
        self.sessions[session_id] = status

    def create_stream(self, rec: StreamRecord) -> None:
        self.streams[rec.stream_id] = rec
        self.last_seq[rec.stream_id] = -1
        self.nonces[rec.stream_id] = set()

    def get_stream(self, stream_id: str) -> StreamRecord | None:
        return self.streams.get(stream_id)

    def take_token(self, stream_id: str) -> float | None:
        now = self.clock()
        tokens, last = self.buckets.get(stream_id, (float(self.burst), now))
        tokens = min(float(self.burst), tokens + (now - last) * self.rate)
        if tokens >= 1:
            self.buckets[stream_id] = (tokens - 1, now)
            return None
        self.buckets[stream_id] = (tokens, now)
        return (1 - tokens) / self.rate

    def accept_batch(self, stream_id: str, seq: int, nonce: str,
                     entry: dict[str, str] | None) -> str:
        rec = self.streams.get(stream_id)
        if rec is None or self.sessions.get(rec.session_id) == "terminated":
            return "unknown_stream"
        last = self.last_seq[stream_id]
        if seq <= last:
            return "duplicate"
        if seq > last + 1:
            return "out_of_order"
        if nonce in self.nonces[stream_id]:
            return "nonce_reused"
        self.last_seq[stream_id] = seq
        self.nonces[stream_id].add(nonce)
        if entry:
            self._counter += 1
            self.events.append((f"{int(time.time() * 1000)}-{self._counter}", dict(entry)))
        return "ok"

    def read_events(self) -> list[tuple[str, dict[str, str]]]:
        return list(self.events)

    def end_user_streams(self, user_id: str, session_ids: list[str]) -> None:
        for stream_id in [s for s, r in self.streams.items() if r.user_id == user_id]:
            for table in (self.streams, self.last_seq, self.nonces, self.buckets):
                table.pop(stream_id, None)
        ended = set(session_ids)
        for session_id in ended:
            if session_id in self.sessions:
                self.sessions[session_id] = "terminated"
        self.events = [(i, f) for i, f in self.events if f.get("session_id") not in ended]

    def end_session_streams(self, session_id: str) -> None:
        for stream_id in [s for s, r in self.streams.items() if r.session_id == session_id]:
            for table in (self.streams, self.last_seq, self.nonces, self.buckets):
                table.pop(stream_id, None)
        if session_id in self.sessions:
            self.sessions[session_id] = "terminated"

    def set_user_channels(self, user_id: str, channels: dict[str, bool]) -> None:
        for stream_id, rec in list(self.streams.items()):
            if rec.user_id == user_id:
                self.streams[stream_id] = replace(rec, channels=dict(channels))


_TAKE_TOKEN = """
local rate = tonumber(ARGV[1])
local burst = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local tokens = burst
local last = now
local raw = redis.call('GET', KEYS[1])
if raw then
  local sep = string.find(raw, ':')
  tokens = tonumber(string.sub(raw, 1, sep - 1))
  last = tonumber(string.sub(raw, sep + 1))
end
tokens = math.min(burst, tokens + (now - last) * rate / 1000)
local wait = 0
if tokens >= 1 then
  tokens = tokens - 1
else
  wait = (1 - tokens) / rate
end
redis.call('SET', KEYS[1], tostring(tokens) .. ':' .. tostring(now), 'PX', ttl)
return tostring(wait)
"""

_ACCEPT = """
if redis.call('EXISTS', KEYS[1]) == 0 then return 'unknown_stream' end
local status = redis.call('HGET', KEYS[3], 'status')
if status == 'terminated' then return 'unknown_stream' end
local last = tonumber(redis.call('HGET', KEYS[1], 'last_seq'))
local seq = tonumber(ARGV[1])
if seq <= last then return 'duplicate' end
if seq > last + 1 then return 'out_of_order' end
if redis.call('SISMEMBER', KEYS[2], ARGV[2]) == 1 then return 'nonce_reused' end
redis.call('HSET', KEYS[1], 'last_seq', ARGV[1])
redis.call('SADD', KEYS[2], ARGV[2])
local ttl = redis.call('PTTL', KEYS[1])
if ttl > 0 then redis.call('PEXPIRE', KEYS[2], ttl) end
if #ARGV > 4 then
  local t = redis.call('TIME')
  local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
  local args = {'XADD', KEYS[4], 'MINID', tostring(now - tonumber(ARGV[3])), '*'}
  for i = 5, #ARGV do args[#args + 1] = ARGV[i] end
  redis.call(unpack(args))
end
if status then redis.call('EXPIRE', KEYS[3], tonumber(ARGV[4])) end
return 'ok'
"""


class RedisHotStore:
    """Production hot state. Expects a client created with ``decode_responses=True``."""

    def __init__(self, client: redis.Redis, rate_per_s: float = DEFAULT_RATE_PER_S,
                 burst: int = DEFAULT_BURST):
        self.client = client
        self.rate, self.burst = float(rate_per_s), burst
        self._take = client.register_script(_TAKE_TOKEN)
        self._accept = client.register_script(_ACCEPT)

    def create_session_state(self, session_id: str) -> None:
        key = session_key(session_id)
        pipe = self.client.pipeline()
        pipe.hset(key, mapping={"status": "active"})
        pipe.expire(key, SESSION_TTL_S)
        pipe.execute()

    def session_status(self, session_id: str) -> str | None:
        return self.client.hget(session_key(session_id), "status")

    def set_session_status(self, session_id: str, status: str) -> None:
        key = session_key(session_id)
        if self.client.exists(key):
            self.client.hset(key, "status", status)

    def create_stream(self, rec: StreamRecord) -> None:
        key = stream_key(rec.stream_id)
        pipe = self.client.pipeline()
        pipe.hset(key, mapping={
            "key": rec.stream_key,
            "session_id": rec.session_id,
            "user_id": rec.user_id,
            "last_seq": -1,
            "channels": json.dumps(rec.channels),
            "pointer_device": rec.pointer_device,
            "expires_at": rec.expires_at.isoformat(),
        })
        pipe.expireat(key, rec.expires_at)
        pipe.execute()

    def get_stream(self, stream_id: str) -> StreamRecord | None:
        data = self.client.hgetall(stream_key(stream_id))
        if not data or "key" not in data:
            return None
        return StreamRecord(
            stream_id=stream_id,
            session_id=data["session_id"],
            user_id=data["user_id"],
            stream_key=data["key"],
            channels=json.loads(data["channels"]),
            pointer_device=data["pointer_device"],
            expires_at=datetime.fromisoformat(data["expires_at"]),
        )

    def take_token(self, stream_id: str) -> float | None:
        wait = float(self._take(keys=[rate_key(stream_id)],
                                args=[self.rate, self.burst, _rate_ttl_ms(self.rate, self.burst)]))
        return None if wait <= 0 else wait

    def accept_batch(self, stream_id: str, seq: int, nonce: str,
                     entry: dict[str, str] | None) -> str:
        rec_session = self.client.hget(stream_key(stream_id), "session_id") or "none"
        args: list = [seq, nonce, RAW_EVENT_RETENTION_MS, SESSION_TTL_S]
        for name, value in (entry or {}).items():
            args.extend([name, value])
        return self._accept(
            keys=[stream_key(stream_id), nonce_key(stream_id), session_key(rec_session), EVENTS_STREAM],
            args=args,
        )

    def read_events(self) -> list[tuple[str, dict[str, str]]]:
        return self.client.xrange(EVENTS_STREAM)

    def _stream_keys_where(self, field: str, value: str) -> list[str]:
        return [key for key in self.client.scan_iter(match="aw:stream:*", count=500)
                if self.client.hget(key, field) == value]

    def _delete_streams(self, keys: list[str]) -> None:
        for key in keys:
            stream_id = key.split(":", 2)[2]
            self.client.delete(key, nonce_key(stream_id), rate_key(stream_id))

    def end_session_streams(self, session_id: str) -> None:
        """Stream keys of the session stop working at once; its raw events stay for the worker."""
        self.set_session_status(session_id, "terminated")
        self._delete_streams(self._stream_keys_where("session_id", session_id))

    def end_user_streams(self, user_id: str, session_ids: list[str]) -> None:
        self._delete_streams(self._stream_keys_where("user_id", user_id))
        for session_id in session_ids:
            self.set_session_status(session_id, "terminated")
        self._purge_session_events(set(session_ids))

    def _purge_session_events(self, session_ids: set[str]) -> None:
        if not session_ids:
            return
        start = "-"
        while True:
            chunk = self.client.xrange(EVENTS_STREAM, min=start, count=500)
            if not chunk:
                return
            doomed = [i for i, f in chunk if f.get("session_id") in session_ids]
            if doomed:
                self.client.xdel(EVENTS_STREAM, *doomed)
            start = "(" + chunk[-1][0]

    def set_user_channels(self, user_id: str, channels: dict[str, bool]) -> None:
        for key in self._stream_keys_where("user_id", user_id):
            self.client.hset(key, "channels", json.dumps(channels))
