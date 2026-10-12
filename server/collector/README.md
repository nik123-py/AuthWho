# server/collector

Event collector (docs/interfaces.md sections 4 to 7). Owner: backend-engineer.

## Run locally

```
docker compose up -d --wait
.venv/Scripts/python -m server.db.migrate --env-file .env
.venv/Scripts/python -m uvicorn server.api.app:app --port 8000 --env-file .env
.venv/Scripts/python -m server.research --env-file .env      # volunteer research export
```

Use `127.0.0.1` rather than `localhost` in `AUTHWHO_DATABASE_URL` and `AUTHWHO_REDIS_URL`: the containers listen on IPv4 only, and on Windows a `localhost` connection first waits for an IPv6 attempt to time out.

## Inspect a manual capture

```
.venv/Scripts/python -m server.collector.dump <session_id> --env-file .env
.venv/Scripts/python -m server.collector.dump <session_id> --json --env-file .env
```

Prints each batch (seq, stream, received time, event count) and each event with its type name and, for key events, the category name. Raw batches expire after 24 hours.

## Batch checks, in order

1. Body over 64 KiB: 413 `too_large`.
2. Body not a JSON object (NaN, Infinity and duplicate keys refused): 400 `schema`. The body is decoded only to find `stream_id`.
3. Unknown or expired stream: 401 `unknown_stream`. HMAC-SHA256 over the raw bytes, constant-time compare: 401 `signature`.
4. Per-stream token bucket, 5 per second with burst 20: 429 `rate_limited` with `retry_after` in seconds and a `Retry-After` header.
5. Strict schema (exact fields, codes 1 to 13 with exact arity, finite numbers, enumerations in range, `session_id` matching the stream): 400 `schema`; more than 500 events: 413.
6. Events of channels disabled for the stream (opt-out or exemption) are dropped before storage.
7. Atomic Lua script: sequence and nonce checks (409 `duplicate`, `out_of_order`, `nonce_reused`), then `XADD aw:events MINID <now - 24 h>` with exact trimming.

Rejected batches never advance `seq`. Error details name positions and rules, never values.
