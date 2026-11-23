"""The exception hierarchy.

WHY THIS FILE EXISTS
--------------------
Services raise DOMAIN errors. They never raise `HTTPException`.

That single rule is what lets `ScanService.execute()` be called from an HTTP request AND from
a background job AND from a test, with no duplication. The moment a service raises
`HTTPException(404)`, it has become coupled to HTTP and the worker can no longer use it —
you'd end up with two copies of the same logic, which then diverge, which is how bugs are born.

Translation to HTTP happens in EXACTLY ONE PLACE: apps/api/middleware/error_handler.py.
Translation to a retry decision happens in exactly one place: the worker's task wrapper.

TWO AXES OF CLASSIFICATION
--------------------------
1. WHAT went wrong  → maps to an HTTP status (NotFoundError → 404).
2. Is it worth RETRYING?  → RetryableError vs PermanentError (docs/07 § Retries).

Axis 2 is the one people forget, and it costs real money: retrying an `AccessDenied` five
times is pure waste, and to the customer's CloudTrail it looks like an attack. Retrying a
`TypeError` in our own code just produces five identical Sentry alerts. Encode the decision
in the TYPE; never leave it to a caller's judgement.

SECURITY NOTE
-------------
`NotFoundError` is raised for BOTH "doesn't exist" AND "belongs to another tenant".
A 403 would confirm the resource exists — an enumeration oracle. See docs/08 § T1.

BANNED, EVERYWHERE IN THIS CODEBASE
-----------------------------------
    except Exception:
        pass

In a security scanner, a swallowed exception becomes "0 findings, score 100" reported to a
customer whose cloud is on fire. If you cannot handle it, let it propagate.

Roadmap: M0 task 0.5.
"""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    """Base class for every error CloudGuard raises deliberately.

    Anything NOT descending from this is, by definition, a bug in our code — which is why
    the error handler maps `DomainError` to a meaningful status and everything else to a
    generic 500 with a Sentry alert. The distinction is load-bearing.
    """

    # Overridden by subclasses. Kept here so the HTTP layer needs no if/elif chain — it just
    # reads `exc.status_code`. Adding a new error type therefore requires ZERO changes to
    # the error handler, which is the point.
    status_code: int = 500
    error_type: str = "internal-error"
    title: str = "Internal Server Error"

    def __init__(self, detail: str, **context: Any) -> None:
        """
        Args:
            detail: Human-readable, SAFE TO SHOW THE USER. Never include internals.
            **context: Structured fields for logs (org_id, resource_id, ...). NOT sent to
                the client. This is how an error carries debugging information without
                leaking it — the two audiences get different data on purpose.
        """
        super().__init__(detail)
        self.detail = detail
        self.context = context


# ---------------------------------------------------------------------------
# Client errors — the caller did something wrong (4xx)
# ---------------------------------------------------------------------------


class ValidationError(DomainError):
    """Input failed a business rule Pydantic cannot express.

    (Pydantic's own schema violations are caught by FastAPI and also become 422 — this is
    for rules like "you cannot suppress a finding without a reason".)
    """

    status_code = 422
    error_type = "validation-error"
    title = "Validation Error"


class AuthenticationError(DomainError):
    """No credentials, or invalid credentials. 'Who are you?'"""

    status_code = 401
    error_type = "authentication-error"
    title = "Authentication Required"


class AuthorizationError(DomainError):
    """Authenticated, but lacks the ROLE for this action. 'I know who you are; you can't.'

    IMPORTANT: this is for ROLE failures only (a `member` trying an `admin` action).
    It is NEVER used for tenancy failures — those are NotFoundError. Returning 403 for a
    resource in another org confirms that the resource EXISTS. See docs/08 § T1.
    """

    status_code = 403
    error_type = "authorization-error"
    title = "Forbidden"


class NotFoundError(DomainError):
    """Resource does not exist — OR belongs to another tenant.

    The conflation is DELIBERATE and is a security control, not sloppiness.
    """

    status_code = 404
    error_type = "not-found"
    title = "Not Found"

    def __init__(self, resource: str, identifier: Any = None, **context: Any) -> None:
        detail = f"{resource} not found"
        super().__init__(detail, resource=resource, identifier=identifier, **context)


class ConflictError(DomainError):
    """The request conflicts with current state. E.g. a scan is already running."""

    status_code = 409
    error_type = "conflict"
    title = "Conflict"


class PlanLimitError(DomainError):
    """The org's subscription plan does not permit this (M8).

    402 rather than 403: the fix is a payment, not a permission. The frontend keys off this
    status to show an upgrade prompt instead of an error toast.
    """

    status_code = 402
    error_type = "plan-limit-exceeded"
    title = "Plan Limit Exceeded"


class RateLimitError(DomainError):
    """Too many requests. The handler adds a `Retry-After` header."""

    status_code = 429
    error_type = "rate-limit-exceeded"
    title = "Too Many Requests"

    def __init__(self, detail: str, retry_after_seconds: int = 60, **context: Any) -> None:
        super().__init__(detail, **context)
        self.retry_after_seconds = retry_after_seconds


# ---------------------------------------------------------------------------
# Integration errors — someone ELSE'S system misbehaved (5xx)
# ---------------------------------------------------------------------------


class IntegrationError(DomainError):
    """An external system (AWS, Claude, Stripe, Resend) failed."""

    status_code = 502
    error_type = "integration-error"
    title = "Upstream Service Error"

    def __init__(self, service: str, detail: str, **context: Any) -> None:
        super().__init__(detail, service=service, **context)
        self.service = service


class RetryableError(IntegrationError):
    """Transient. Back off and try again.

    Examples: AWS throttling, a 503 from Anthropic, a network timeout, a Postgres
    serialization failure. The worker's task wrapper inspects the TYPE and applies
    exponential backoff with jitter. See docs/07 § Retries.
    """

    error_type = "retryable-error"


class PermanentError(IntegrationError):
    """Will NEVER succeed on retry. Fail fast; dead-letter it.

    The canonical example is `AccessDenied` on AssumeRole: the customer's IAM role is
    misconfigured. Retrying five times wastes our time, hammers their STS endpoint, and
    lights up their CloudTrail like an attack. It is not a technical failure — it is a
    PRODUCT EVENT, and the correct response is to mark the account `error` and email their
    admin. See docs/07.
    """

    error_type = "permanent-error"
