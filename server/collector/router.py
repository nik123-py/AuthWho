"""Collector endpoints (docs/interfaces.md sections 4 and 6).

Responses never include event values or keys, and nothing here logs a request
body. Raw batches go only to the Redis stream ``aw:events``; PostgreSQL holds
users and sessions only.
"""

from __future__ import annotations

import hmac
import json
import logging
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from starlette.concurrency import run_in_threadpool

from server.collector import schema, signing
from server.collector.hot_store import StreamRecord
from server.collector.repository import UserRecord
from server.common.redis_keys import STREAM_TTL_S
from server.research.files import DeletionIncomplete, delete_user_folder

log = logging.getLogger("authwho.collector")
router = APIRouter()

Channel = Literal["keystroke", "pointer", "interaction"]
PointerDevice = Literal["mouse", "touchpad", "unknown"]


class ApiError(Exception):
    def __init__(self, status: int, body: dict, headers: dict | None = None):
        self.status, self.body, self.headers = status, body, headers


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(exc.body, status_code=exc.status, headers=exc.headers)


def _state(request: Request):
    return request.app.state


def require_app_key(request: Request,
                    x_authwho_app_key: Annotated[str | None, Header()] = None) -> None:
    expected = _state(request).settings.require("app_api_key").encode()
    given = (x_authwho_app_key or "").encode("utf-8", "replace")
    if not hmac.compare_digest(expected, given):
        raise ApiError(401, {"error": "unauthorized"})


AppKey = Depends(require_app_key)


class ConsentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_id: str = Field(min_length=1, max_length=64)
    role: str = Field(min_length=1, max_length=64)
    consent_version: str = Field(min_length=1, max_length=32)
    consent_at: datetime
    research_consent: StrictBool
    opt_outs: list[Channel] = Field(max_length=3)
    pointer_device: PointerDevice


class SessionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: uuid.UUID
    app_id: str = Field(min_length=1, max_length=64)
    role: str = Field(min_length=1, max_length=64)


class EndBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=64)


def _delete_research_folder(research_dir, user_id: str) -> None:
    """Never report success while research data remains; the caller retries on 503."""
    try:
        delete_user_folder(research_dir, user_id)
    except DeletionIncomplete:
        log.error("research folder deletion incomplete")
        raise ApiError(503, {"error": "deletion_incomplete"}, {"Retry-After": "1"})


def channels_for(user: UserRecord) -> dict[str, bool]:
    return {c: (not user.exempt) and c not in user.opt_outs for c in schema.CHANNELS}


# ---- users ---------------------------------------------------------------------------------

@router.put("/v1/users/{user_id}", dependencies=[AppKey])
def put_user(user_id: uuid.UUID, body: ConsentBody, request: Request):
    st = _state(request)
    uid = str(user_id)
    record = UserRecord(uid, body.app_id, body.role, body.consent_version, body.consent_at,
                        body.research_consent, sorted(set(body.opt_outs)), False,
                        body.pointer_device)
    # Same clock as the batches' received_at, so the research export compares like with like.
    previous = st.repository.upsert_user(record, now=datetime.now(timezone.utc))
    if not body.research_consent:
        # Also on a repeated PUT, so a retry after 503 finishes the deletion.
        _delete_research_folder(st.research_dir, uid)
    if previous is not None:
        stored = st.repository.get_user(uid)
        if stored is not None:
            st.hot_store.set_user_channels(uid, channels_for(stored))
    return {"user_id": uid}


@router.delete("/v1/users/{user_id}", status_code=204, dependencies=[AppKey])
def delete_user(user_id: uuid.UUID, request: Request):
    st = _state(request)
    uid = str(user_id)
    session_ids = st.repository.delete_user(uid)
    st.hot_store.end_user_streams(uid, session_ids)
    _delete_research_folder(st.research_dir, uid)
    return Response(status_code=204)


# ---- sessions and streams ------------------------------------------------------------------

@router.post("/v1/sessions", status_code=201, dependencies=[AppKey])
def create_session(body: SessionBody, request: Request):
    st = _state(request)
    uid = str(body.user_id)
    if st.repository.get_user(uid) is None:
        raise ApiError(409, {"error": "no_consent"})
    session_id = str(uuid.uuid4())
    st.repository.create_session(session_id, uid, body.app_id, body.role)
    st.hot_store.create_session_state(session_id)
    return {"session_id": session_id}


@router.post("/v1/sessions/{session_id}/streams", status_code=201, dependencies=[AppKey])
def create_stream(session_id: uuid.UUID, request: Request):
    st = _state(request)
    session = st.repository.get_session(str(session_id))
    if session is None:
        raise ApiError(404, {"error": "unknown_session"})
    if session.status == "terminated":
        raise ApiError(409, {"error": "session_ended"})
    user = st.repository.get_user(session.user_id)
    if user is None:
        raise ApiError(409, {"error": "no_consent"})
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=STREAM_TTL_S)
    rec = StreamRecord(
        stream_id=str(uuid.uuid4()),
        session_id=session.session_id,
        user_id=user.user_id,
        stream_key=signing.new_stream_key(),
        channels=channels_for(user),
        pointer_device=user.pointer_device,
        expires_at=expires_at,
    )
    st.hot_store.create_stream(rec)
    return {
        "stream_id": rec.stream_id,
        "stream_key": rec.stream_key,
        "expires_at": expires_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "channels": rec.channels,
        "pointer_device": rec.pointer_device,
    }


@router.post("/v1/sessions/{session_id}/end", dependencies=[AppKey])
def end_session(session_id: uuid.UUID, body: EndBody, request: Request):
    """Section 11: end a session. Idempotent; its stream keys stop working at once."""
    st = _state(request)
    sid = str(session_id)
    if not st.repository.end_session(sid):
        raise ApiError(404, {"error": "unknown_session"})
    st.hot_store.end_session_streams(sid)
    return {"status": "terminated"}


# ---- batches -------------------------------------------------------------------------------

TOO_LARGE = ApiError(413, {"error": "too_large"})


async def _read_capped(request: Request) -> bytes:
    length = request.headers.get("content-length")
    if length is not None and (not length.isdigit() or int(length) > schema.MAX_BODY_BYTES):
        raise TOO_LARGE
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > schema.MAX_BODY_BYTES:
            raise TOO_LARGE
        chunks.append(chunk)
    return b"".join(chunks)


def _reject(status: int, body: dict, reason: str, headers: dict | None = None) -> ApiError:
    log.info("batch rejected: %s", reason)
    return ApiError(status, body, headers)


def process_batch(st, raw: bytes, signature: str | None) -> dict:
    try:
        obj = schema.parse_json(raw)
    except schema.SchemaError as exc:
        raise _reject(400, {"error": "schema", "detail": str(exc)}, "schema")
    stream_id = obj.get("stream_id")
    try:
        stream_id = str(uuid.UUID(stream_id)) if isinstance(stream_id, str) else None
    except ValueError:
        stream_id = None
    if stream_id is None:
        raise _reject(400, {"error": "schema", "detail": "stream_id must be a UUID string"}, "schema")
    rec = st.hot_store.get_stream(stream_id)
    if rec is None:
        raise _reject(401, {"error": "unknown_stream"}, "unknown_stream")
    if not signing.verify(rec.stream_key, raw, signature):
        raise _reject(401, {"error": "signature"}, "signature")
    wait = st.hot_store.take_token(stream_id)
    if wait is not None:
        retry_after = round(max(wait, 0.001), 3)
        raise _reject(429, {"error": "rate_limited", "retry_after": retry_after}, "rate_limited",
                      {"Retry-After": str(max(1, math.ceil(wait)))})
    try:
        batch = schema.validate_batch(obj)
    except schema.TooLarge:
        raise _reject(413, {"error": "too_large"}, "too_large")
    except schema.SchemaError as exc:
        raise _reject(400, {"error": "schema", "detail": str(exc)}, "schema")
    if batch.session_id != rec.session_id:
        raise _reject(400, {"error": "schema", "detail": "session_id does not match the stream"},
                      "schema")
    # Defence in depth: events of a channel the user opted out of are never stored.
    events = [e for e in batch.events if rec.channels.get(schema.channel_of(e[0]), False)]
    entry = None
    if events:
        entry = {
            "session_id": batch.session_id,
            "stream_id": batch.stream_id,
            "seq": str(batch.seq),
            "received_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "pointer_device": batch.pointer_device,
            "events": json.dumps(events, separators=(",", ":")),
        }
    result = st.hot_store.accept_batch(stream_id, batch.seq, batch.nonce, entry)
    if result == "unknown_stream":
        raise _reject(401, {"error": "unknown_stream"}, "unknown_stream")
    if result != "ok":
        raise _reject(409, {"error": "replay", "reason": result}, result)
    return {"accepted": True, "seq": batch.seq}


@router.post("/v1/batches", status_code=202)
async def post_batch(request: Request,
                     x_authwho_signature: Annotated[str | None, Header()] = None):
    raw = await _read_capped(request)
    return await run_in_threadpool(process_batch, _state(request), raw, x_authwho_signature)
