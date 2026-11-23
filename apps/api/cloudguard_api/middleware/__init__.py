"""HTTP middleware.

ORDER MATTERS — AND IT IS COUNTER-INTUITIVE.

Starlette applies middleware in REVERSE order of registration: the LAST one you add is the
OUTERMOST layer, the first to see a request and the last to see a response.

We register:  AccessLog, then RequestId
Which yields: RequestId (outer) → AccessLog → CORS → router

That is the order we need. `RequestIdMiddleware` must run FIRST so that the request_id is
bound to contextvars BEFORE `AccessLogMiddleware` emits a single line — otherwise our access
logs would be the only logs in the system without a correlation id, which is exactly backwards.

Get this ordering wrong and nothing crashes; you just quietly lose the ability to correlate.
That is the worst kind of bug, so it is written down here.

M0 ships RequestId + AccessLog + error handlers.
M1 adds authentication. M8 adds the Redis token-bucket rate limiter.
"""

from cloudguard_api.middleware.error_handler import register_exception_handlers
from cloudguard_api.middleware.logging import AccessLogMiddleware
from cloudguard_api.middleware.request_id import RequestIdMiddleware

__all__ = ["AccessLogMiddleware", "RequestIdMiddleware", "register_exception_handlers"]
