"""ARQ worker entrypoint.

Run: `arq cloudguard_worker.main.WorkerSettings`

GRACEFUL SHUTDOWN — AN M0 DELIVERABLE, AND THE ONE PEOPLE SKIP
--------------------------------------------------------------
Every deploy sends SIGTERM. Without a graceful shutdown, SIGTERM kills the worker mid-job.
In M4 that means: **every deploy kills every running scan.** The customer sees a scan stuck
at "running" forever, and the only reason they don't see it stuck FOREVER-forever is the
`reap_stuck_scans` cron we're required to write in M4 (docs/07).

ARQ's contract: on SIGTERM it stops accepting NEW jobs and waits for in-flight ones to finish,
up to `--graceful-timeout`. Only then does `on_shutdown` run and the process exit. We set the
timeout to 60s (constants.GRACEFUL_SHUTDOWN_SECONDS).

Note this is a BEST-EFFORT drain, not a guarantee — a scan can legitimately take 15 minutes,
far longer than any platform's shutdown grace period. Which is exactly why tasks must ALSO be
idempotent and re-runnable (tasks/__init__.py). Two independent mechanisms, because one of
them will eventually not be enough.

QUEUES (docs/07)
----------------
M0 runs a single default queue — there is one task and it does nothing. M4 splits into
`scans` / `default` / `reports`, so that one enterprise customer's 20,000-resource scan cannot
occupy every worker slot and leave every other customer's dashboard sitting at "queued".
That split is cheap insurance against your best customer degrading everyone else.
"""

from __future__ import annotations

from typing import Any, ClassVar

from arq.connections import RedisSettings

from cloudguard_core.config import get_settings
from cloudguard_core.constants import DEFAULT_JOB_TIMEOUT_SECONDS
from cloudguard_worker.context import on_shutdown, on_startup
from cloudguard_worker.tasks import ping


def _redis_settings() -> RedisSettings:
    """Translate our REDIS_URL into ARQ's connection settings.

    One source of truth for configuration (core/config.py). ARQ wants its own object; fine —
    we adapt at the edge rather than introducing a second way to configure Redis.
    """
    return RedisSettings.from_dsn(str(get_settings().redis_url))


class WorkerSettings:
    """ARQ reads this class by convention (it is not instantiated)."""

    # ClassVar: this is a MUTABLE class attribute, and ruff's RUF012 is right to flag a bare
    # `list` here. It is genuinely shared state — every worker in the process reads the same
    # list — so we declare that intent rather than letting it look like an instance field
    # someone could safely mutate.
    functions: ClassVar[list[Any]] = [ping]

    on_startup = on_startup
    on_shutdown = on_shutdown

    redis_settings = _redis_settings()

    # How many jobs this process runs CONCURRENTLY. These are async coroutines, not threads,
    # so the ceiling is I/O — a scan spends nearly all its wall-clock time waiting on AWS API
    # calls, not burning CPU. 10 is a conservative starting point; M4 tunes per queue.
    max_jobs = 10

    job_timeout = DEFAULT_JOB_TIMEOUT_SECONDS

    # Keep completed job results in Redis for an hour, so `GET /v1/scans/{id}` can report on
    # a job that finished moments ago without a database round-trip.
    keep_result = 3600

    # Global default. M4 overrides PER FAILURE CLASS — retrying an AccessDenied is pure waste
    # and looks like an attack in the customer's CloudTrail (docs/07 § Retries).
    max_tries = 3

    # Health check row in Redis, so an operator can see the worker is alive. The worker has no
    # HTTP surface by design (docs/08 § T3), so it cannot serve a /healthz of its own.
    health_check_interval = 30
