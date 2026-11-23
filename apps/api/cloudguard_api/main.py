"""FastAPI application factory — the composition root of the HTTP process.

WHY A FACTORY (`create_app()`) AND NOT A MODULE-LEVEL `app = FastAPI()`
----------------------------------------------------------------------
A module-level app is constructed at IMPORT time. That means:
  - importing the module in a test spins up the real app with the real settings;
  - you cannot build two apps with different configuration in one test session;
  - `dependency_overrides` become a global mutation shared across tests.

A factory means a test can do `create_app(settings=test_settings)` and get a clean,
isolated instance. It costs one function and it buys testability for the life of the project.

LIFESPAN: WHERE EXPENSIVE THINGS ARE BORN AND BURIED
----------------------------------------------------
The DB engine and Redis pool are created ONCE at startup and stashed on `app.state`.
Creating an engine per request would create a connection pool per request and exhaust
Postgres in seconds.

GRACEFUL SHUTDOWN (an M0 deliverable, and easy to get wrong)
------------------------------------------------------------
Every deploy sends SIGTERM. Without a lifespan teardown:
  - open Postgres connections are severed rather than closed, leaving the server to time them
    out — you slowly leak connections across deploys until you hit `max_connections`;
  - in-flight requests are killed mid-response, and a customer sees a network error caused by
    a deploy they had no part in.

The `yield` in `lifespan` is the shutdown seam: uvicorn stops accepting new connections,
drains in-flight requests, and only THEN runs the code after `yield`. The worker has its own
version of this (docs/07 § Failure recovery), which is what stops a deploy from killing a
running scan.

Roadmap: M0 task 0.7.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from cloudguard_api.middleware import (
    AccessLogMiddleware,
    RequestIdMiddleware,
    register_exception_handlers,
)
from cloudguard_api.routers import health
from cloudguard_core.config import Settings, get_settings
from cloudguard_core.db.session import create_engine, create_session_factory
from cloudguard_core.logging import configure_logging, get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown. Everything before `yield` runs once, at boot."""
    settings: Settings = app.state.settings

    # --- STARTUP ---
    engine = create_engine(settings)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)

    # `decode_responses=True`: give us `str`, not `bytes`. Without it every read needs a
    # `.decode()` and you find the one you forgot in production.
    app.state.redis = Redis.from_url(str(settings.redis_url), decode_responses=True)

    log.info(
        "api.started",
        environment=settings.environment.value,
        docs_enabled=settings.docs_enabled,
    )

    yield  # ← the application serves traffic here

    # --- SHUTDOWN (runs after in-flight requests have drained) ---
    log.info("api.shutting_down")
    await app.state.redis.aclose()
    await engine.dispose()  # close every pooled connection CLEANLY
    log.info("api.stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application. The only place the HTTP stack is assembled."""
    settings = settings or get_settings()

    # Configure logging FIRST — before anything else can emit a line in the wrong format.
    configure_logging(settings)

    app = FastAPI(
        title="CloudGuard AI API",
        version="0.1.0",
        description="Cloud security that fixes itself.",
        lifespan=lifespan,
        # Hidden in production. The OpenAPI schema is a complete, machine-readable map of
        # every endpoint, parameter and error — invaluable in dev, gratuitous attack-surface
        # disclosure in prod. The frontend consumes it at BUILD time (`make types`), never at
        # runtime, so nothing breaks by hiding it. (config.py § docs_enabled)
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,  # we ship one docs UI, not two
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.settings = settings

    # --- Middleware ---------------------------------------------------------
    # ⚠️ REVERSE ORDER: the LAST registered is the OUTERMOST.
    # Registering AccessLog then RequestId yields the execution order:
    #     RequestId (outer) → AccessLog → CORS → router
    # RequestId MUST be outermost so the request_id is bound to contextvars before the access
    # log emits anything. See middleware/__init__.py.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,  # explicit list — NEVER "*" with credentials
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Idempotency-Key"],
        expose_headers=["X-Request-ID"],  # so the browser can read it back for support
    )
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIdMiddleware)

    # --- Exception handlers -------------------------------------------------
    # The ONLY place an error response is formatted (middleware/error_handler.py).
    register_exception_handlers(app)

    # --- Routers ------------------------------------------------------------
    # Health is deliberately NOT under /v1: probes are infrastructure, not product API, and
    # must not break when we ship /v2.
    app.include_router(health.router)

    # From M1, domain routers mount under API_PREFIX ("/v1"):
    #     app.include_router(cloud_accounts.router, prefix=API_PREFIX)

    return app


# The ASGI entrypoint uvicorn imports: `uvicorn cloudguard_api.main:app`.
# Calling the factory here is fine — this module is imported once, by the server.
app = create_app()
