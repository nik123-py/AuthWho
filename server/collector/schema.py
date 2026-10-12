"""Strict batch and event schema (docs/interfaces.md sections 5 and 6).

Every event is a list of finite numbers whose first element is an integer
event code. Error messages name positions and rules only; they never contain
a value from the batch, so they are safe to return and to log.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
import re
import uuid
from dataclasses import dataclass
from typing import Any

MAX_EVENTS = 500
MAX_BODY_BYTES = 64 * 1024
MAX_SAFE_INT = 2**53
POINTER_DEVICES = ("mouse", "touchpad", "unknown")
CHANNELS = ("keystroke", "pointer", "interaction")

CATEGORY_NAMES = {
    1: "letter",
    2: "digit",
    3: "space",
    4: "backspace",
    5: "modifier",
    6: "navigation",
    7: "other",
}

# Field rules: "num" any finite number, "count" a non-negative integer,
# or a frozenset of allowed integer values.
_NUM = "num"
_COUNT = "count"
_BUTTON = frozenset({0, 1, 2})


@dataclass(frozen=True)
class EventType:
    name: str
    channel: str
    fields: tuple[str, ...]  # names, including "code"
    rules: tuple[Any, ...]  # one rule per field after "code"


EVENT_TYPES: dict[int, EventType] = {
    1: EventType("KEY_DOWN", "keystroke", ("code", "t", "category", "press_id"),
                 (_NUM, frozenset(CATEGORY_NAMES), _COUNT)),
    2: EventType("KEY_UP", "keystroke", ("code", "t", "category", "press_id"),
                 (_NUM, frozenset(CATEGORY_NAMES), _COUNT)),
    3: EventType("POINTER_MOVE", "pointer", ("code", "t", "x", "y"), (_NUM, _NUM, _NUM)),
    4: EventType("POINTER_DOWN", "pointer", ("code", "t", "x", "y", "button"),
                 (_NUM, _NUM, _NUM, _BUTTON)),
    5: EventType("POINTER_UP", "pointer", ("code", "t", "x", "y", "button"),
                 (_NUM, _NUM, _NUM, _BUTTON)),
    6: EventType("WHEEL", "interaction", ("code", "t", "delta_x", "delta_y", "delta_mode"),
                 (_NUM, _NUM, _NUM, frozenset({0, 1, 2}))),
    7: EventType("SCROLL", "interaction", ("code", "t", "scroll_x", "scroll_y"), (_NUM, _NUM, _NUM)),
    8: EventType("FIELD_FOCUS", "interaction", ("code", "t", "field_index", "field_kind"),
                 (_NUM, _COUNT, frozenset(range(1, 10)))),
    9: EventType("FIELD_BLUR", "interaction", ("code", "t", "field_index"), (_NUM, _COUNT)),
    10: EventType("VISIBILITY", "interaction", ("code", "t", "state"), (_NUM, frozenset({0, 1}))),
    11: EventType("CLIPBOARD", "interaction", ("code", "t", "action"), (_NUM, frozenset({1, 2, 3}))),
    12: EventType("PAGE", "interaction", ("code", "t", "page_code"), (_NUM, _COUNT)),
    13: EventType("ACTION_MARK", "interaction", ("code", "t", "action_code"), (_NUM, _COUNT)),
}

_TOP_LEVEL = ("v", "session_id", "stream_id", "seq", "nonce", "sent_at", "pointer_device", "events")
_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{22}(==)?$")


class SchemaError(ValueError):
    """The batch violates the schema. The message never contains batch values."""


class TooLarge(ValueError):
    """The batch is over the event-count or byte limit."""


@dataclass(frozen=True)
class Batch:
    v: int
    session_id: str
    stream_id: str
    seq: int
    nonce: str  # canonical base64url without padding
    sent_at: float
    pointer_device: str
    events: list[list[int | float]]


def channel_of(code: int) -> str:
    return EVENT_TYPES[code].channel


def _reject_constant(_name: str):
    raise SchemaError("non-finite numbers are not allowed")


def _no_duplicates(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise SchemaError("duplicate field")
        obj[key] = value
    return obj


def parse_json(raw: bytes) -> dict:
    """Decode a request body into a JSON object, refusing NaN, Infinity and duplicate keys."""
    try:
        text = raw.decode("utf-8")
        obj = json.loads(text, parse_constant=_reject_constant, object_pairs_hook=_no_duplicates)
    except SchemaError:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise SchemaError("body is not valid JSON") from exc
    if not isinstance(obj, dict):
        raise SchemaError("body must be a JSON object")
    return obj


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return -MAX_SAFE_INT <= value <= MAX_SAFE_INT
    return isinstance(value, float) and math.isfinite(value)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and -MAX_SAFE_INT <= value <= MAX_SAFE_INT


def _integral(value: Any) -> bool:
    return _is_int(value) or (isinstance(value, float) and math.isfinite(value) and value.is_integer())


def _check_rule(value: Any, rule: Any) -> bool:
    if rule == _NUM:
        return True
    if not _integral(value):
        return False
    if rule == _COUNT:
        return value >= 0
    return int(value) in rule


def _validate_event(index: int, event: Any) -> None:
    where = f"events[{index}]"
    if not isinstance(event, list) or not event:
        raise SchemaError(f"{where}: an event must be a non-empty array")
    for pos, value in enumerate(event):
        if not _is_number(value):
            raise SchemaError(f"{where}[{pos}]: elements must be finite numbers")
    code = event[0]
    if not _is_int(code) or code not in EVENT_TYPES:
        raise SchemaError(f"{where}: unknown event code")
    spec = EVENT_TYPES[code]
    if len(event) != len(spec.fields):
        raise SchemaError(f"{where}: wrong number of elements for {spec.name}")
    for pos, (value, rule) in enumerate(zip(event[1:], spec.rules), start=1):
        if not _check_rule(value, rule):
            raise SchemaError(f"{where}[{pos}]: {spec.fields[pos]} is out of range for {spec.name}")


def _uuid(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise SchemaError(f"{name} must be a UUID string")
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        raise SchemaError(f"{name} must be a UUID string") from exc


def _nonce(value: Any) -> str:
    if not isinstance(value, str) or not _NONCE_RE.match(value):
        raise SchemaError("nonce must be 16 bytes in base64url")
    bare = value.rstrip("=")
    try:
        decoded = base64.urlsafe_b64decode(bare + "==")
    except (binascii.Error, ValueError) as exc:
        raise SchemaError("nonce must be 16 bytes in base64url") from exc
    if len(decoded) != 16 or base64.urlsafe_b64encode(decoded).decode().rstrip("=") != bare:
        raise SchemaError("nonce must be 16 bytes in base64url")
    return bare


def validate_batch(obj: Any) -> Batch:
    if not isinstance(obj, dict):
        raise SchemaError("body must be a JSON object")
    unknown = set(obj) - set(_TOP_LEVEL)
    if unknown:
        raise SchemaError("unknown field in batch")
    missing = [name for name in _TOP_LEVEL if name not in obj]
    if missing:
        raise SchemaError(f"missing field: {missing[0]}")
    if not _is_int(obj["v"]) or obj["v"] != 1:
        raise SchemaError("v must be 1")
    if not _is_int(obj["seq"]) or obj["seq"] < 0:
        raise SchemaError("seq must be a non-negative integer")
    if not _is_number(obj["sent_at"]):
        raise SchemaError("sent_at must be a finite number")
    if obj["pointer_device"] not in POINTER_DEVICES or not isinstance(obj["pointer_device"], str):
        raise SchemaError("pointer_device must be mouse, touchpad or unknown")
    events = obj["events"]
    if not isinstance(events, list):
        raise SchemaError("events must be an array")
    if len(events) > MAX_EVENTS:
        raise TooLarge("more than 500 events")
    for index, event in enumerate(events):
        _validate_event(index, event)
    return Batch(
        v=1,
        session_id=_uuid("session_id", obj["session_id"]),
        stream_id=_uuid("stream_id", obj["stream_id"]),
        seq=obj["seq"],
        nonce=_nonce(obj["nonce"]),
        sent_at=float(obj["sent_at"]),
        pointer_device=obj["pointer_device"],
        events=events,
    )
