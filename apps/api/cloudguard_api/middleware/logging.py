"""Access logging.

WHY WE REPLACE UVICORN'S ACCESS LOG
-----------------------------------
Uvicorn emits:

    INFO:  127.0.0.1:52341 - "GET /v1/findings/018f-abc HTTP/1.1" 200

A sentence. Three problems, all of which get worse as we grow:

  1. NOT QUERYABLE. "What is the p95 latency of the findings list?" cannot be answered by
     regexing sentences.
  2. HIGH-CARDINALITY PATHS. `/v1/findings/018f-abc` is a UNIQUE string per finding. Feed
     that to a metrics backend as a label and you get millions of distinct time series — this
     is called a cardinality explosion and it is how teams get a surprise five-figure
     observability bill. We log the ROUTE TEMPLATE (`/v1/findings/{finding_id}`) instead,
     and put the id in a separate field.
  3. NO CORRELATION. No request_id, no org_id.

WHAT WE DELIBERATELY DO **NOT** LOG
-----------------------------------
Request bodies. Response bodies. Headers.
A request body will one day contain a suppression reason, an email address, or — via a
webhook — a Stripe payload. A header contains `Authorization`. Logging any of them turns our
log aggregator into a secondary store of customer PII and credentials, with none of the
controls we apply to the database (docs/08 § Secrets). The redaction processor in
core/logging.py is a net for accidents; not logging them is the policy.
"""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from cloudguard_core.logging import get_logger

log = get_logger("api.access")


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            # An exception that escapes to here means the error handler did not catch it —
            # i.e. a genuine bug. Log it as an access event (so latency data isn't lost) and
            # re-raise; Starlette's ServerErrorMiddleware turns it into a 500 and Sentry
            # captures it. We never swallow it (docs/11 § Errors).
            duration_ms = (time.perf_counter() - start) * 1000
            log.exception(
                "http.request.failed",
                method=request.method,
                path=_route_template(request),
                duration_ms=round(duration_ms, 2),
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000

        # Healthchecks fire every 10s per container. At INFO they would drown every real
        # event in the log. DEBUG keeps them available without the noise.
        level = "debug" if request.url.path in ("/healthz", "/readyz") else "info"

        # request_id and (from M1) org_id are merged in automatically by structlog's
        # contextvars processor — bound once in RequestIdMiddleware, free everywhere.
        getattr(log, level)(
            "http.request",
            method=request.method,
            path=_route_template(request),
            status=response.status_code,
            duration_ms=round(duration_ms, 2),
        )
        return response


def _route_template(request: Request) -> str:
    """Return `/v1/findings/{finding_id}`, not `/v1/findings/018f-abc`.

    See point 2 in the module docstring: raw paths are unbounded-cardinality labels and will
    detonate a metrics backend. `request.scope["route"]` is populated by Starlette's router
    AFTER matching; on a 404 there is no route, so we fall back to the raw path (404s are
    bounded in practice, and knowing WHAT was requested is the point of logging them).
    """
    route = request.scope.get("route")
    if route is not None and hasattr(route, "path"):
        return str(route.path)
    return request.url.path
