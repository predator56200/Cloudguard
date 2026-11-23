"""Exception handlers — the ONLY place in the codebase that formats an error response.

WHY CENTRALISE
--------------
If each router formats its own errors, you get four subtly different error shapes, the
frontend needs four code paths, and the fifth endpoint someone writes invents a fifth shape.
One handler = one contract, forever, and adding an endpoint cannot break it.

THE CONTRACT: RFC 7807 `application/problem+json` (docs/05 § Error handling)

    {
      "type":   "https://cloudguard.ai/errors/plan-limit-exceeded",
      "title":  "Plan Limit Exceeded",
      "status": 402,
      "detail": "Your Starter plan allows 1 connected AWS account.",
      "instance": "/v1/cloud-accounts",
      "request_id": "018f-...",
      "errors": [{"field": "aws_account_id", "message": "..."}]
    }

Why a standard rather than our own shape? Because `type` is a stable, machine-readable URI:
the frontend can branch on `plan-limit-exceeded` to show an upgrade dialog instead of an
error toast, and that branch keeps working even when we reword `detail`. Inventing a bespoke
error format is a decision you regret at exactly the moment it is expensive to change.

⚠️ THE SECURITY RULE — WE ARE A SECURITY COMPANY
------------------------------------------------
An unhandled exception returns EXACTLY:

    {"type": "internal-error", "title": "Internal Server Error", "status": 500,
     "detail": "An unexpected error occurred.", "request_id": "018f-..."}

Never the exception message. Never a stack trace. A stack trace in an HTTP response is a free
architecture diagram for an attacker: framework versions, file paths, ORM internals, table
names. The real detail goes to our logs (and Sentry from M8), correlated by `request_id` —
so support can still say "give me that id" and see everything.

NOTE the layering payoff: this handler contains NO if/elif chain over error types. It reads
`exc.status_code`, `exc.error_type`, `exc.title` off the exception class itself
(core/errors.py). Adding a new error type in M4 requires ZERO changes to this file.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from cloudguard_core.errors import DomainError, RateLimitError
from cloudguard_core.logging import get_logger

log = get_logger(__name__)

PROBLEM_JSON = "application/problem+json"
ERROR_TYPE_BASE = "https://cloudguard.ai/errors"


def _problem(
    *,
    status_code: int,
    error_type: str,
    title: str,
    detail: str,
    request: Request,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build one RFC 7807 problem document. Every error in the system flows through here."""
    body: dict[str, Any] = {
        "type": f"{ERROR_TYPE_BASE}/{error_type}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": request.url.path,
        # Always present. This is what a customer quotes in a support ticket and what we
        # search on. It is the whole reason RequestIdMiddleware exists.
        "request_id": getattr(request.state, "request_id", None),
    }
    if extra:
        body.update(extra)
    return JSONResponse(
        status_code=status_code, content=body, media_type=PROBLEM_JSON, headers=headers
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Wire all handlers. Called once from the app factory."""

    @app.exception_handler(DomainError)
    async def _domain_error(request: Request, exc: DomainError) -> JSONResponse:
        """Every error we raise DELIBERATELY (core/errors.py).

        Note: `exc.detail` IS returned to the client — these messages are written to be safe
        and useful ("Your Starter plan allows 1 connected AWS account"). `exc.context` is
        NOT: it holds org_ids, resource ids and internals, and goes only to the logs. Two
        audiences, two payloads, on purpose.
        """
        headers = None
        if isinstance(exc, RateLimitError):
            # RFC 6585: tell the client WHEN to come back, so a well-behaved client backs
            # off instead of hammering us into a worse state.
            headers = {"Retry-After": str(exc.retry_after_seconds)}

        # 4xx = the caller's problem (info). 5xx = OUR problem (error, wakes someone).
        level = "warning" if exc.status_code < 500 else "error"
        getattr(log, level)(
            "request.domain_error",
            error_type=exc.error_type,
            status=exc.status_code,
            detail=exc.detail,
            **exc.context,
        )

        return _problem(
            status_code=exc.status_code,
            error_type=exc.error_type,
            title=exc.title,
            detail=exc.detail,
            request=request,
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Pydantic schema violations → 422 with per-field messages.

        FastAPI's default returns a raw Pydantic error list, which leaks internal model
        structure and does not match our contract. We normalise it into the SAME problem+json
        shape as everything else, so the frontend has exactly one error path.
        """
        errors = [
            {
                # loc is like ("body", "aws_account_id"); drop the "body"/"query" prefix —
                # the client doesn't care where in OUR parsing it failed.
                "field": ".".join(str(p) for p in err["loc"][1:]) or str(err["loc"][0]),
                "message": err["msg"],
            }
            for err in exc.errors()
        ]
        log.info("request.validation_error", errors=errors)

        return _problem(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_type="validation-error",
            title="Validation Error",
            detail="The request body or parameters failed validation.",
            request=request,
            extra={"errors": errors},
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        """The catch-all. An exception reaching here is BY DEFINITION A BUG IN OUR CODE —
        anything we anticipated would be a DomainError.

        `log.exception` captures the full traceback for US. The CLIENT gets nothing but a
        generic message and a request_id. See the security rule in the module docstring.
        """
        log.exception(
            "request.unhandled_error",
            error_class=type(exc).__name__,
            path=request.url.path,
        )
        return _problem(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_type="internal-error",
            title="Internal Server Error",
            detail="An unexpected error occurred.",  # ← deliberately uninformative
            request=request,
        )
