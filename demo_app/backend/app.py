"""Demo web application backend (``docs/interfaces.md`` section 15).

Run locally with::

    .venv/Scripts/python -m uvicorn demo_app.backend.app:app --port 8100 --env-file .env

The demo app never disables, locks or deletes an account. Usernames and
passwords stay in this service; AuthWho only sees the pseudonymous
``authwho_user_id``.

Continuous authentication (P4): every request from a login with an AuthWho
session first checks the session status. A session AuthWho has ended logs the
user out (``session_ended``); while a step-up is required, notes and
high-risk actions answer ``step_up_required``. High-risk actions ask AuthWho's
policy first. The step-up is a TOTP code when the user has set one up, and the
account password otherwise; three wrong answers in a row count as a failed
check, which ends the session. If AuthWho cannot be reached, normal session
rules apply and nothing is blocked.
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
from server.common.production import require_production_ready

from .config import Settings
from .passwords import burn_time, hash_password, verify_password
from . import totp
from .registry import ACTIONS, registry_payload
from .withdrawals import complete_withdrawal, run_retry_loop
from .store import CHANNELS, Consent, LoginSession, Store, User, UsernameTaken, now_iso

APP_ID = "demo"
COOKIE_NAME = "demo_session"
MAX_STEP_UP_FAILURES = 3

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


class TotpCode(BaseModel):
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=12)]


class StepUp(BaseModel):
    code: Annotated[str, StringConstraints(strip_whitespace=True, max_length=12)] | None = None
    password: Annotated[str, StringConstraints(max_length=1024)] | None = None


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


class SessionEnded(Exception):
    pass


class StepUpRequired(Exception):
    def __init__(self, method: str):
        self.method = method


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
        require_production_ready()
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

    @app.exception_handler(SessionEnded)
    def _session_ended(request: Request, exc: SessionEnded) -> JSONResponse:
        response = _error(401, "session_ended")
        response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax")
        return response

    @app.exception_handler(StepUpRequired)
    def _step_up_required(request: Request, exc: StepUpRequired) -> JSONResponse:
        return JSONResponse(status_code=403, content={"error": "step_up_required", "method": exc.method})

    def current_login(request: Request) -> LoginSession:
        token = request.cookies.get(COOKIE_NAME)
        login_session = store.get_login_session(token, settings.session_hours) if token else None
        if login_session is None:
            raise NotLoggedIn
        return login_session

    CurrentLogin = Annotated[LoginSession, Depends(current_login)]

    def step_up_method(user: User) -> str:
        return "totp" if settings.totp_key is not None and user.totp_enabled else "password"

    def end_login(login_session: LoginSession) -> None:
        store.delete_login_session(login_session.token_hash)
        raise SessionEnded

    def session_status(login_session: LoginSession) -> str:
        """AuthWho's status for this login; ``active`` without capture or when AuthWho is unreachable."""
        if login_session.authwho_session_id is None:
            return "active"
        try:
            return collector.session_status(login_session.authwho_session_id)
        except CollectorUnavailable:
            logger.warning("AuthWho unreachable for a status check; normal session rules apply")
            return "active"

    def checked_login(request: Request) -> LoginSession:
        login_session = current_login(request)
        status = session_status(login_session)
        if status == "terminated":
            end_login(login_session)
        request.state.authwho_status = status
        return login_session

    CheckedLogin = Annotated[LoginSession, Depends(checked_login)]

    def no_pending_step_up(request: Request, login_session: LoginSession) -> None:
        if getattr(request.state, "authwho_status", "active") == "step_up_required":
            raise StepUpRequired(step_up_method(login_session.user))

    def allow_action(request: Request, login_session: LoginSession, action: str) -> None:
        """Ask AuthWho's policy before a high-risk action (section 11)."""
        no_pending_step_up(request, login_session)
        if login_session.authwho_session_id is None:
            return  # no behavioural capture: normal session rules
        try:
            decision = collector.check_action(login_session.authwho_session_id, action, ACTIONS[action].sensitivity)
        except CollectorUnavailable:
            logger.warning("AuthWho unreachable for an action check; normal session rules apply")
            return
        if decision["outcome"] == "terminate":
            end_login(login_session)
        if not decision["action_allowed"]:
            raise StepUpRequired(step_up_method(login_session.user))

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
        # Secure only when configured: local development is plain HTTP on localhost (section 2).
        response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax", path="/",
                            secure=settings.secure_cookies, max_age=int(settings.session_hours * 3600))
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
    def me(login_session: CheckedLogin):
        user = login_session.user
        return {
            "username": user.username,
            "consent": _consent_json(user.consent),
            "withdrawal_pending": withdrawal_still_pending(user),
            "totp_enabled": user.totp_enabled,
        }

    @app.post("/api/consent")
    def give_consent(body: ConsentBody, login_session: CheckedLogin):
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
    def withdraw_consent(login_session: CheckedLogin):
        user = login_session.user
        # Capture stops locally at once and the pending flag is stored durably,
        # so the AuthWho deletion is retried later if it cannot finish now.
        store.withdraw_consent(user.id)
        if not complete_withdrawal(store, collector, user.id, user.authwho_user_id):
            return _error(502, "authwho_unavailable")
        return Response(status_code=204)

    @app.post("/api/authwho/stream")
    def authwho_stream(login_session: CheckedLogin):
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
            "endpoint": settings.public_collector_url or settings.collector_url,
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
    def notes(body: Note, request: Request, login_session: CheckedLogin):
        no_pending_step_up(request, login_session)
        # The text is discarded on purpose: the page exists only to produce typing.
        return Response(status_code=204)

    @app.post("/api/payees")
    def add_payee(body: Payee, request: Request, login_session: CheckedLogin):
        allow_action(request, login_session, "add_payee")
        return {"ok": True}

    @app.post("/api/reports/export")
    def export_report(request: Request, login_session: CheckedLogin):
        allow_action(request, login_session, "export_report")
        return {"ok": True}

    @app.get("/api/session")
    def session_state(request: Request, login_session: CheckedLogin):
        return {"status": request.state.authwho_status, "method": step_up_method(login_session.user)}

    @app.post("/api/totp/setup")
    def totp_setup(login_session: CheckedLogin):
        user = login_session.user
        if settings.totp_key is None:
            return _error(503, "totp_unavailable")
        if user.totp_enabled:
            return _error(409, "totp_already_enabled")
        secret = totp.new_secret()
        store.set_totp_secret(user.id, totp.encrypt_secret(secret, settings.totp_key, user.authwho_user_id))
        payload = {"secret": secret, "otpauth_uri": totp.provisioning_uri(secret, user.username)}
        return JSONResponse(payload, headers={"Cache-Control": "no-store"})

    @app.post("/api/totp/confirm")
    def totp_confirm(body: TotpCode, login_session: CheckedLogin):
        user = login_session.user
        if settings.totp_key is None or user.totp_secret_enc is None:
            return _error(409, "no_totp_setup")
        secret = totp.decrypt_secret(user.totp_secret_enc, settings.totp_key, user.authwho_user_id)
        if not totp.verify(secret, body.code):
            return _error(400, "invalid_code")
        store.enable_totp(user.id)
        return {"totp_enabled": True}

    @app.post("/api/step-up")
    def step_up(body: StepUp, request: Request, login_session: CheckedLogin):
        user = login_session.user
        if request.state.authwho_status != "step_up_required" or login_session.authwho_session_id is None:
            return _error(409, "no_step_up_pending")
        if step_up_method(user) == "totp":
            secret = totp.decrypt_secret(user.totp_secret_enc, settings.totp_key, user.authwho_user_id)
            passed = totp.verify(secret, body.code or "")
        else:
            passed = body.password is not None and verify_password(body.password, user.password_hash,
                                                                   user.password_salt)
        sid = login_session.authwho_session_id
        if passed:
            store.reset_step_up_failures(login_session.token_hash)
            try:
                collector.report_step_up(sid, True)
            except CollectorUnavailable:
                return _error(502, "authwho_unavailable")
            return {"status": "active"}
        failures = store.add_step_up_failure(login_session.token_hash)
        if failures < MAX_STEP_UP_FAILURES:
            return JSONResponse(status_code=400, content={"error": "step_up_failed",
                                                          "attempts_left": MAX_STEP_UP_FAILURES - failures})
        try:
            collector.report_step_up(sid, False)
        except CollectorUnavailable:
            logger.warning("AuthWho unreachable when reporting a failed step-up; ending the login anyway")
        end_login(login_session)

    return app


app = create_app()
