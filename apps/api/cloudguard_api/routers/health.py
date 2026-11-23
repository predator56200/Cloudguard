"""Health endpoints.

THE MOST IMPORTANT IDEA IN THIS FILE: LIVENESS ≠ READINESS.

They look identical and they are not. Conflating them causes a specific, nasty outage that
looks like this:

    Postgres has a 30-second blip.
    Your single /health endpoint checks the DB, so it starts returning 503.
    The orchestrator's LIVENESS probe reads that 503 as "process is broken" and KILLS the
    container. Then the new one starts, still can't reach the DB, and gets killed too.
    Now you are in a crash-loop, no container survives long enough to reconnect, and a
    30-second database blip has become a 20-minute total outage that you caused.

The fix is two endpoints with two different meanings:

    /healthz  LIVENESS  — "is this process alive?"
              Checks NOTHING external. Returns 200 as long as the event loop can respond.
              Wired to the orchestrator's RESTART policy.
              A failure here means: restart me. It is the only sane trigger for a restart.

    /readyz   READINESS — "can this process usefully serve traffic RIGHT NOW?"
              Checks DB + Redis. Wired to the LOAD BALANCER.
              A failure here means: stop sending me traffic — but LEAVE ME RUNNING, because
              I will recover on my own the moment the database comes back.

A DB blip should remove a container from the load balancer. It should never restart it.

Roadmap: M0 task 0.7. docs/02 § Configuration & startup.
"""

from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from cloudguard_api.deps import RedisClient, RedisDep, SessionFactoryDep
from cloudguard_core import __version__
from cloudguard_core.db.session import check_database
from cloudguard_core.logging import get_logger

log = get_logger(__name__)

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Liveness. Deliberately trivial."""

    status: Literal["ok"] = "ok"
    version: str


class ReadinessResponse(BaseModel):
    """Readiness, with a per-dependency breakdown.

    The breakdown matters operationally: "not ready" tells you to page someone;
    `{"database": "ok", "redis": "unavailable"}` tells you WHO to page and skips the first
    ten minutes of an incident.
    """

    status: Literal["ready", "not_ready"]
    version: str
    checks: dict[str, Literal["ok", "unavailable"]]


@router.get("/healthz", response_model=HealthResponse, summary="Liveness probe")
async def healthz() -> HealthResponse:
    """Is the process alive?

    Checks NOTHING external — that is the entire point (see the module docstring). If this
    handler can execute and return, the event loop is responsive and the process is healthy.
    A dependency failure must NEVER be able to trigger a restart from here.

    Used by: Docker HEALTHCHECK, Railway's restart policy, k8s livenessProbe.
    """
    return HealthResponse(version=__version__)


@router.get("/readyz", response_model=ReadinessResponse, summary="Readiness probe")
async def readyz(
    session_factory: SessionFactoryDep,
    redis: RedisDep,
    response: Response,
) -> ReadinessResponse:
    """Can this process usefully serve traffic right now?

    Checks Postgres and Redis CONCURRENTLY (`asyncio.gather`), not sequentially: a readiness
    probe runs every few seconds on every container and must be fast. Sequential checks add
    their latencies; concurrent checks take the max. It is free, so do it.

    Returns 503 when a dependency is down, which pulls this container OUT of the load
    balancer while LEAVING IT RUNNING to recover.
    """
    db_ok, redis_ok = await asyncio.gather(
        check_database(session_factory),
        _check_redis(redis),
    )

    checks: dict[str, Literal["ok", "unavailable"]] = {
        "database": "ok" if db_ok else "unavailable",
        "redis": "ok" if redis_ok else "unavailable",
    }
    ready = db_ok and redis_ok

    if not ready:
        # 503 + Retry-After is the honest, standards-compliant way to say "not me, not now".
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        response.headers["Retry-After"] = "5"
        log.warning("readiness.failed", checks=checks)

    return ReadinessResponse(
        status="ready" if ready else "not_ready", version=__version__, checks=checks
    )


async def _check_redis(redis: RedisClient) -> bool:
    """PING Redis.

    A broad `except Exception` here is one of the very few places it is CORRECT (contrast
    docs/11 § Errors, which bans it). A readiness probe must never itself raise: an exception
    would become a 500, and a 500 from /readyz is indistinguishable to a load balancer from a
    500 caused by a real bug. Its job is to report a boolean, always.
    """
    try:
        await redis.ping()
        return True
    except Exception as exc:  # noqa: BLE001 — deliberate; see docstring
        log.warning("readiness.redis_unavailable", error=str(exc))
        return False
