"""Print one session's raw batches from ``aw:events`` for manual inspection.

Usage::

    .venv/Scripts/python -m server.collector.dump <session_id> [--json] [--env-file .env]

For each batch it prints seq, received time and event count, then every event
with its type name and, for key events, the category name. This is the owner's
tool for checking a manual capture; it reads Redis only and writes nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid

import redis

from server.collector.schema import CATEGORY_NAMES, EVENT_TYPES
from server.common.config import load_env_file
from server.common.redis_keys import EVENTS_STREAM


def describe_event(event: list) -> dict:
    spec = EVENT_TYPES.get(event[0]) if event else None
    if spec is None or len(event) != len(spec.fields):
        return {"type": "UNKNOWN", "values": event}
    out = {"type": spec.name}
    for name, value in zip(spec.fields[1:], event[1:]):
        out[name] = CATEGORY_NAMES.get(value, value) if name == "category" else value
    return out


def _batch(fields: dict) -> dict:
    events = json.loads(fields.get("events", "[]"))
    return {
        "seq": int(fields.get("seq", -1)),
        "stream_id": fields.get("stream_id"),
        "received_at": fields.get("received_at"),
        "event_count": len(events),
        "events": [describe_event(e) for e in events],
    }


def format_batches(entries: list[tuple[str, dict]], as_json: bool = False) -> str:
    batches = [_batch(fields) for _, fields in entries]
    if as_json:
        return json.dumps(batches, indent=2)
    lines = []
    for b in batches:
        lines.append(f"batch seq={b['seq']} stream={b['stream_id']} "
                     f"received_at={b['received_at']} events={b['event_count']}")
        for e in b["events"]:
            lines.append("  " + " ".join([e["type"]] + [f"{k}={v}" for k, v in e.items()
                                                          if k != "type"]))
    return "\n".join(lines)


def read_session_entries(client: redis.Redis, session_id: str) -> list[tuple[str, dict]]:
    found, start = [], "-"
    while True:
        chunk = client.xrange(EVENTS_STREAM, min=start, count=500)
        if not chunk:
            return found
        found += [(i, f) for i, f in chunk if f.get("session_id") == session_id]
        start = "(" + chunk[-1][0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print one session's batches from aw:events.")
    parser.add_argument("session_id")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    parser.add_argument("--env-file", help="read missing variables from this file, for example .env")
    args = parser.parse_args(argv)
    try:
        session_id = str(uuid.UUID(args.session_id))
    except ValueError:
        print("session_id must be a UUID", file=sys.stderr)
        return 2
    if args.env_file:
        load_env_file(args.env_file)
    url = os.environ.get("AUTHWHO_REDIS_URL")
    if not url:
        print("AUTHWHO_REDIS_URL is not set", file=sys.stderr)
        return 2
    client = redis.Redis.from_url(url, decode_responses=True)
    try:
        entries = read_session_entries(client, session_id)
    finally:
        client.close()
    output = format_batches(entries, as_json=args.json)
    if output:
        print(output)
    elif not args.json:
        print("no batches for this session in aw:events (entries expire after 24 hours)",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
