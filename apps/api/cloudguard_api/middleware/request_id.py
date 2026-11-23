"""Request-ID middleware — the single most useful field in an incident.

WHY
---
A customer emails: "my scan failed around 14:02, here's a screenshot." Without a correlation
id you are grepping timestamps across three services. With one, you paste the id from the
screenshot into your log search and read the entire story — API request, service call,
enqueued job, worker execution, the AWS error — in order, across processes.

HOW IT PROPAGATES
-----------------
1. Accept an inbound `X-Request-ID` if the caller sent one (so a trace started at the CDN or
   in the browser survives into our logs — never break someone else's trace).
2. Otherwise mint a UUIDv7. Time-sortable, so ids are chronologically ordered even before
   you look at the timestamp.
3. `bind_contextvars` it — every structlog line for the rest of this request now carries it
   automatically, at any call depth, with no plumbing (see core/logging.py).
4. Echo it back in the response header, so a client — and a customer's screenshot — can
   report it.

⚠️ `clear_contextvars()` at the START of every request, not just the end.
Middleware runs in an asyncio task. Tasks can be reused. If a previous request crashed hard
enough to skip its cleanup, its `org_id` could linger in the contextvars of the NEXT request
and get stamped onto logs belonging to a DIFFERENT TENANT. That is a (log-level) tenant
leak. Clearing on the way IN is unconditional and cannot be skipped by an exception.

Roadmap: M0 task 0.7 (middleware). docs/02 § Request lifecycle, step 2.
"""

from __future__ import annotations

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from cloudguard_core.constants import REQUEST_ID_HEADER
from cloudguard_core.ids import uuid7


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Clear FIRST. See the warning in the module docstring — this is a correctness
        # requirement, not tidiness.
        structlog.contextvars.clear_contextvars()

        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid7())

        # Stash on request.state so exception handlers can reach it without re-parsing
        # headers (the RFC 7807 problem document includes it — see error_handler.py).
        request.state.request_id = request_id

        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
