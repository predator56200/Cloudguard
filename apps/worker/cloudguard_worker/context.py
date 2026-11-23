"""Worker composition root.

The mirror image of `apps/api/deps.py`. Between the two files, they are the ONLY places in
the backend that know how to construct a service. Everything else just receives one.

WHY THE WORKER BUILDS THE SAME OBJECTS AS THE API
-------------------------------------------------
Because `ScanService` does not know, and must not care, whether it was invoked by an HTTP
request or a cron tick. If the worker built a *different* ScanService — with a different
session, or a bypassed RLS context — then "scan" would mean two different things and the two
would drift. That is precisely the duplication the layering exists to prevent.

⚠️ RLS APPLIES TO THE WORKER TOO.
There is a tempting shortcut here: "the worker is internal, it's trusted, let it query
without a tenant context." That shortcut is how the four-layer isolation model (docs/08)
becomes a three-layer model with a hole in it. The worker opens its sessions through the SAME
`session_scope(factory, org_id=...)` as the API. It has no privileged path. If a bug in a
task ever queries the wrong tenant, Postgres refuses — same as everywhere else.

ARQ gives each worker process a `ctx` dict, populated in `on_startup` and passed to every
job. That dict is our injection mechanism: the engine and Redis pool are created ONCE per
process, not once per job.
"""

from __future__ import annotations

from typing import Any

from cloudguard_core.config import Settings, get_settings
from cloudguard_core.db.session import create_engine, create_session_factory
from cloudguard_core.logging import configure_logging, get_logger

log = get_logger(__name__)


async def on_startup(ctx: dict[str, Any]) -> None:
    """Runs once when the worker process boots. Builds the shared, expensive objects.

    Creating an engine per JOB would create a connection pool per job and exhaust Postgres
    within minutes of a busy scan schedule.
    """
    settings: Settings = get_settings()

    # Same logging config as the API, so an API log line and a worker log line for the same
    # scan are joinable on `request_id`. Two log formats across two services makes
    # distributed debugging guesswork.
    configure_logging(settings)

    engine = create_engine(settings)
    ctx["settings"] = settings
    ctx["engine"] = engine
    ctx["session_factory"] = create_session_factory(engine)

    log.info("worker.started", environment=settings.environment.value)


async def on_shutdown(ctx: dict[str, Any]) -> None:
    """Runs on SIGTERM, AFTER in-flight jobs have finished (see main.py § graceful shutdown).

    Closing the engine severs the pool cleanly. Without this, every deploy leaks Postgres
    connections until the server times them out — and you only notice when you hit
    `max_connections` at the worst possible moment.
    """
    log.info("worker.shutting_down")
    await ctx["engine"].dispose()
    log.info("worker.stopped")
