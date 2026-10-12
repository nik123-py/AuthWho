"""Redis key names and lifetimes (docs/interfaces.md section 7)."""

from __future__ import annotations

EVENTS_STREAM = "aw:events"
RAW_EVENT_RETENTION_MS = 24 * 3600 * 1000
STREAM_TTL_S = 24 * 3600
SESSION_TTL_S = 24 * 3600


def stream_key(stream_id: str) -> str:
    return f"aw:stream:{stream_id}"


def nonce_key(stream_id: str) -> str:
    return f"aw:nonce:{stream_id}"


def rate_key(stream_id: str) -> str:
    return f"aw:rate:{stream_id}"


def session_key(session_id: str) -> str:
    return f"aw:session:{session_id}"


def raw_event_min_id(now_ms: int) -> str:
    """Smallest stream ID allowed to survive: anything older than 24 hours goes."""
    return str(now_ms - RAW_EVENT_RETENTION_MS)


# Pub/Sub channel for trust updates and decisions (dashboard WebSocket).
TRUST_CHANNEL = "aw:trust"
