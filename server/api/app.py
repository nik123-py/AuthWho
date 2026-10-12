"""AuthWho API application: ``server.api.app:app``.

Run locally with::

    .venv/Scripts/python -m uvicorn server.api.app:app --port 8000 --env-file .env

Configuration comes from environment variables (docs/interfaces.md section 3).
Tests call ``create_app`` with injected settings and stores.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import redis
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from server.collector.hot_store import RedisHotStore
from server.collector.repository import PostgresRepository
from server.collector.router import ApiError, api_error_handler
from server.collector.router import router as collector_router
from server.common.config import Settings, load_settings
from server.research.files import DEFAULT_RESEARCH_DIR


async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    # Report where and which rule failed, never the submitted value.
    parts = [".".join(str(p) for p in err.get("loc", ())) + ": " + err.get("type", "invalid")
             for err in exc.errors()]
    return JSONResponse({"error": "schema", "detail": "; ".join(parts)}, status_code=400)


def create_app(settings: Settings | None = None, hot_store=None, repository=None,
               research_dir: Path | None = None) -> FastAPI:
    settings = settings if settings is not None else load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        client = None
        if app.state.hot_store is None:
            client = redis.Redis.from_url(settings.require("redis_url"), decode_responses=True)
            app.state.hot_store = RedisHotStore(client)
        if app.state.repository is None:
            app.state.repository = PostgresRepository(settings.require("database_url"))
        try:
            yield
        finally:
            if client is not None:
                client.close()

    app = FastAPI(title="AuthWho API", lifespan=lifespan)
    app.state.settings = settings
    app.state.hot_store = hot_store
    app.state.repository = repository
    app.state.research_dir = Path(research_dir) if research_dir else DEFAULT_RESEARCH_DIR
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["POST"],
        allow_headers=["Content-Type", "X-AuthWho-Signature"],
        allow_credentials=False,
        max_age=600,
    )
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.include_router(collector_router)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    return app


app = create_app()
