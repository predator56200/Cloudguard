"""`ping` — the M0 smoke task (roadmap task 0.8).

Its only job is to prove, end to end, that:
    API/CLI → Redis → ARQ worker → structured log
is wired correctly, BEFORE we build anything that depends on it. If the queue is broken, you
want to discover that now — with a 10-line task — not in M4 while debugging a 200-line scan
pipeline and wondering which of the two is at fault.

It also demonstrates the shape EVERY future task takes (docs/02 § Job lifecycle):

    async def task(ctx, ...args) -> Result:
        1. read collaborators from `ctx` (built once in context.py)
        2. open a TENANT-SCOPED session
        3. call ONE core service method       ← the actual work lives there, not here
        4. return a small, serialisable result

A task is a thin adapter, exactly like an HTTP router. If `run_scan` (M4) ever grows business
logic inside this folder, it is in the wrong layer — and the tell is that the API could no
longer trigger the same behaviour.
"""

from __future__ import annotations

from typing import Any

from cloudguard_core.logging import get_logger

log = get_logger(__name__)


async def ping(ctx: dict[str, Any], message: str = "pong") -> dict[str, str]:
    """Prove the queue works.

    `ctx["job_id"]` is injected by ARQ. We bind it to the log line because in M4 a customer
    will ask "why did my scan fail?" and the answer starts with finding their job.
    """
    log.info("task.ping", job_id=ctx.get("job_id"), message=message)
    return {"status": "ok", "message": message}
