"""Admin API and live feed for the dashboard (docs/interfaces.md section 13).

Every endpoint needs ``Authorization: Bearer <AUTHWHO_ADMIN_TOKEN>``; the
WebSocket takes the same token as the ``token`` query parameter, because
browsers cannot set headers on a WebSocket. Responses hold pseudonymous ids,
scores, levels, feature names and explanations, never raw events.
"""

from __future__ import annotations

import asyncio
import hmac
import uuid
from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, WebSocket
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from server.collector.router import ApiError

router = APIRouter(prefix="/v1/admin")


def _token_ok(request_app, given: str | None) -> bool:
    expected = (request_app.state.settings.admin_token or "").encode()
    return bool(expected) and hmac.compare_digest(expected, (given or "").encode("utf-8", "replace"))


def require_admin(request: Request, authorization: Annotated[str | None, Header()] = None) -> None:
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    if not _token_ok(request.app, token):
        raise ApiError(401, {"error": "unauthorized"})


Admin = Depends(require_admin)


def _repo(request: Request):
    return request.app.state.admin_repo


def _known(request: Request, session_id: uuid.UUID) -> str:
    sid = str(session_id)
    if _repo(request).session(sid) is None:
        raise ApiError(404, {"error": "unknown_session"})
    return sid


@router.get("/sessions", dependencies=[Admin])
def sessions(request: Request, limit: int = 50):
    return _repo(request).list_sessions(max(1, min(limit, 500)))


@router.get("/sessions/{session_id}/timeline", dependencies=[Admin])
def timeline(session_id: uuid.UUID, request: Request):
    return _repo(request).timeline(_known(request, session_id))


@router.get("/sessions/{session_id}/decisions", dependencies=[Admin])
def decisions(session_id: uuid.UUID, request: Request):
    return _repo(request).decisions(_known(request, session_id))


def contributing_features(points: list[dict]) -> list[dict]:
    """Features named among the top deviations of scored channels, most frequent first."""
    seen: dict[tuple[str, str], dict] = defaultdict(lambda: {"times": 0, "max_abs_z": 0.0})
    for p in points:
        for channel, c in (p.get("channels") or {}).items():
            for f in c.get("top_features") or []:
                entry = seen[(channel, f["name"])]
                entry["times"] += 1
                entry["max_abs_z"] = max(entry["max_abs_z"], abs(float(f["z"])))
    rows = [{"channel": ch, "name": n, **v} for (ch, n), v in seen.items()]
    return sorted(rows, key=lambda r: (-r["times"], -r["max_abs_z"]))


@router.get("/sessions/{session_id}/incident-report", dependencies=[Admin])
def incident_report(session_id: uuid.UUID, request: Request):
    sid = _known(request, session_id)
    repo = _repo(request)
    points = repo.timeline(sid)
    trusts = [p["trust"] for p in points if p.get("trust") is not None]
    report = {
        "report": "AuthWho incident report",
        "session": repo.session(sid),
        "summary": {
            "trust_points": len(points),
            "lowest_trust": min(trusts) if trusts else None,
            "contributing_features": contributing_features(points)[:10],
        },
        "timeline": points,
        "decisions": repo.decisions(sid),
    }
    return JSONResponse(report, headers={"Content-Disposition": f'attachment; filename="incident-{sid}.json"'})


class PolicyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    high: float = Field(gt=0, le=100)
    strong: float = Field(ge=0, lt=100)
    channel_low: float = Field(gt=0, lt=1)
    action_sensitivity: dict[str, str]
    exempt: bool


@router.get("/policies", dependencies=[Admin])
def policies(request: Request):
    return _repo(request).policies()


@router.put("/policies/{policy_id}", dependencies=[Admin])
def update_policy(policy_id: str, body: PolicyBody, request: Request):
    if body.strong >= body.high:
        raise ApiError(400, {"error": "invalid_policy", "detail": "strong must be below high"})
    if any(v not in ("low", "medium", "high") for v in body.action_sensitivity.values()):
        raise ApiError(400, {"error": "invalid_policy", "detail": "sensitivity must be low, medium or high"})
    updated = _repo(request).update_policy(policy_id, body.model_dump())
    if updated is None:
        raise ApiError(404, {"error": "unknown_policy"})
    return updated


@router.websocket("/ws")
async def live(websocket: WebSocket):
    if not _token_ok(websocket.app, websocket.query_params.get("token")):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    feed = websocket.app.state.trust_feed

    async def forward() -> None:
        async for message in feed.subscribe():
            await websocket.send_text(message)

    async def until_disconnect() -> None:
        # A quiet feed never sends, so only reading tells us the browser has gone.
        while (await websocket.receive())["type"] != "websocket.disconnect":
            pass

    tasks = {asyncio.create_task(forward()), asyncio.create_task(until_disconnect())}
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()  # closes the feed's subscription when the browser leaves
        await asyncio.gather(*tasks, return_exceptions=True)


class RedisTrustFeed:
    """Trust updates and decisions published by the worker and the session API on ``aw:trust``."""

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url

    async def subscribe(self):
        import redis.asyncio as aioredis

        from server.common.redis_keys import TRUST_CHANNEL

        client = aioredis.Redis.from_url(self.redis_url, decode_responses=True)
        pubsub = client.pubsub()
        await pubsub.subscribe(TRUST_CHANNEL)
        try:
            async for msg in pubsub.listen():
                if msg.get("type") == "message":
                    yield msg["data"]
        finally:
            await pubsub.aclose()
            await client.aclose()

