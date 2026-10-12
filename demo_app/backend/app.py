"""Demo web application backend (``docs/interfaces.md`` section 15).

Run locally with::

    .venv/Scripts/python -m uvicorn demo_app.backend.app:app --port 8100 --env-file .env

The demo app never disables, locks or deletes an account. Usernames and
passwords stay in this service; AuthWho only sees the pseudonymous
``authwho_user_id``.
"""

import asyncio
import logging
import threading
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import httpx
from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StringConstraints

from .authwho_client import CollectorClient, CollectorNoConsent, CollectorUnavailable
from .config import Settings
from .passwords import burn_time, hash_password, verify_password
from .registry import registry_payload
from .withdrawals import complete_withdrawal, run_retry_loop
from .store import CHANNELS, Consent, LoginSession, Store, User, UsernameTaken, now_iso

APP_ID = "demo"
COOKIE_NAME = "demo_session"

logger = logging.getLogger(__name__)

Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
Password = Annotated[str, StringConstraints(min_length=8, max_length=1024)]


class Credentials(BaseModel):
    username: Username
    password: Password


class Note(BaseModel):
    # Typed only to produce free-text typing; never stored or logged.
    text: Annotated[str, StringConstraints(max_length=20_000)]


class Payee(BaseModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    account: Annotated[str, StringConstraints(min_length=1, max_length=64)]


class Channels(BaseModel):
    keystroke: bool
    pointer: bool
    interaction: bool


class ConsentBody(BaseModel):
    version: Annotated[str, StringConstraints(min_length=1, max_length=16)]
    channels: Channels
    research_consent: bool
    pointer_device: Literal["mouse", "touchpad"]


def _consent_json(consent: Consent | None) -> dict | None:
    if consent is None:
        return None
    return {
        "version": consent.version,
        "at": consent.at,
        "channels": consent.channels,
        "research_consent": consent.research_consent,
        "pointer_device": consent.pointer_device,
    }


def _error(status_code: int, code: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": code})


def _field_name(loc) -> str:
    parts = [str(part) for part in loc if part != "body"]
    return ".".join(parts) or "body"


class NotLoggedIn(Exception):
    pass


def create_app(settings: Settings | None = None, collector_http: httpx.Client | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    store = Store(settings.db_path)
    if collector_http is None:
        collector_http = httpx.Client(timeout=5.0)
    collector = CollectorClient(collector_http, settings.collector_url, settings.app_api_key)
    # Serialises "create the AuthWho session once per login" across concurrent page loads.
    session_lock = threading.Lock()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Background retry of pending consent withdrawals, so users who never
        # come back are still deleted from AuthWho.
        stop = asyncio.Event()
        task = asyncio.create_task(
            run_retry_loop(store, collector, settings.withdrawal_retry_seconds, stop)
        )
        try:
            yield
        finally:
            stop.set()
            await task

    app = FastAPI(title="AuthWho demo app backend", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    def _invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI's default body echoes the submitted input, which may be a
        # password or note text, so only the names of the bad fields are returned.
        fields = sorted({_field_name(err.get("loc", ())) for err in exc.errors()})
        return JSONResponse(status_code=422, content={"error": "invalid_request", "fields": fields})

    @app.exception_handler(NotLoggedIn)
    def _not_logged_in(request: Request, exc: NotLoggedIn) -> JSONResponse:
        return _error(401, "not_logged_in")

    def current_login(request: Request) -> LoginSession:
        token = request.cookies.get(COOKIE_NAME)
        login_session = store.get_login_session(token) if token else None
        if login_session is None:
            raise NotLoggedIn
        return login_session

    CurrentLogin = Annotated[LoginSession, Depends(current_login)]

    def withdrawal_still_pending(user: User) -> bool:
        """Retry an unconfirmed withdrawal; True while AuthWho has still not confirmed it."""
        return user.withdrawal_pending and not complete_withdrawal(
            store, collector, user.id, user.authwho_user_id
        )

    @app.post("/api/register", status_code=201)
    def register(body: Credentials):
        password_hash, salt = hash_password(body.password)
        try:
            user = store.create_user(body.username, password_hash, salt)
        except UsernameTaken:
            return _error(409, "username_taken")
        return {"username": user.username}

    @app.post("/api/login")
    def login(body: Credentials, response: Response):
        user = store.get_user(body.username)
        if user is None:
            burn_time()
            return _error(401, "invalid_credentials")
        if not verify_password(body.password, user.password_hash, user.password_salt):
            return _error(401, "invalid_credentials")
        withdrawal_still_pending(user)  # best effort; login never depends on AuthWho
        token = store.create_login_session(user)
        # Not marked Secure: local development is plain HTTP on localhost (section 2).
        response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax", path="/")
        return {"username": user.username, "needs_consent": user.consent is None}

    @app.post("/api/logout", status_code=204)
    def logout(login_session: CurrentLogin, response: Response):
        store.delete_login_session(login_session.token_hash)
        if login_session.authwho_session_id is not None:
            try:
                collector.end_session(login_session.authwho_session_id, "logout")
            except CollectorUnavailable:
                # The demo login is already gone; AuthWho expires the stream keys on its own.
                logger.warning("Could not end the AuthWho session at logout")
        response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax")

    @app.get("/api/me")
    def me(login_session: CurrentLogin):
        user = login_session.user
        return {
            "username": user.username,
            "consent": _consent_json(user.consent),
            "withdrawal_pending": withdrawal_still_pending(user),
        }

    @app.post("/api/consent")
    def give_consent(body: ConsentBody, login_session: CurrentLogin):
        user = login_session.user
        # A stale AuthWho row from an unfinished withdrawal must be deleted
        # before new consent is recorded, never reused.
        if withdrawal_still_pending(user):
            return _error(502, "authwho_unavailable")
        channels = body.channels.model_dump()
        consent = Consent(
            version=body.version,
            at=now_iso(),
            channels=channels,
            research_consent=body.research_consent,
            pointer_device=body.pointer_device,
        )
        # Forward first and store only once AuthWho has accepted, so the two
        # records never disagree about whether capture is allowed.
        try:
            collector.put_user(
                user.authwho_user_id,
                {
                    "app_id": APP_ID,
                    "role": user.role,
                    "consent_version": consent.version,
                    "consent_at": consent.at,
                    "research_consent": consent.research_consent,
                    "opt_outs": [name for name in CHANNELS if not channels[name]],
                    "pointer_device": consent.pointer_device,
                },
            )
        except CollectorUnavailable:
            return _error(502, "authwho_unavailable")
        store.save_consent(user.id, consent)
        return _consent_json(consent)

    @app.delete("/api/consent", status_code=204)
    def withdraw_consent(login_session: CurrentLogin):
        user = login_session.user
        # Capture stops locally at once and the pending flag is stored durably,
        # so the AuthWho deletion is retried later if it cannot finish now.
        store.withdraw_consent(user.id)
        if not complete_withdrawal(store, collector, user.id, user.authwho_user_id):
            return _error(502, "authwho_unavailable")
        return Response(status_code=204)

    @app.post("/api/authwho/stream")
    def authwho_stream(login_session: CurrentLogin):
        user = login_session.user
        if user.consent is None:
            return _error(409, "no_consent")
        try:
            with session_lock:
                session_id = store.get_authwho_session_id(login_session.token_hash)
                if session_id is None:
                    session_id = collector.create_session(user.authwho_user_id, APP_ID, user.role)
                    store.set_authwho_session_id(login_session.token_hash, session_id)
            stream = collector.create_stream(session_id)
        except CollectorNoConsent:
            return _error(409, "no_consent")
        except CollectorUnavailable:
            return _error(502, "authwho_unavailable")
        payload = {
            "endpoint": settings.collector_url,
            "session_id": session_id,
            "stream_id": stream["stream_id"],
            "stream_key": stream["stream_key"],
            "channels": stream["channels"],
            "pointer_device": stream["pointer_device"],
        }
        # The stream key must never be kept by browser or proxy caches.
        return JSONResponse(payload, headers={"Cache-Control": "no-store"})

    @app.get("/api/registry")
    def registry():
        return registry_payload()

    @app.post("/api/notes", status_code=204)
    def notes(body: Note, login_session: CurrentLogin):
        # The text is discarded on purpose: the page exists only to produce typing.
        return Response(status_code=204)

    @app.post("/api/payees")
    def add_payee(body: Payee, login_session: CurrentLogin):
        # High-risk action. The policy check through AuthWho is added in P4.
        return {"ok": True}

    @app.post("/api/reports/export")
    def export_report(login_session: CurrentLogin):
        # High-risk action. The policy check through AuthWho is added in P4.
        return {"ok": True}

    return app


app = create_app()
