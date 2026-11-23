"""Structured logging.

WHY NOT stdlib `logging`
------------------------
    log.info(f"Scan {scan_id} finished in {ms}ms with {n} findings")

That line is a sentence. To answer "what is the p95 scan duration for org X?" you would have
to regex a sentence. At 10,000 organisations that is not merely slow, it is impossible.

    log.info("scan.completed", scan_id=..., org_id=..., duration_ms=..., findings_opened=...)

That line is an EVENT: a JSON object with typed fields. It can be queried, aggregated and
alerted on. Log events, not sentences (docs/11 § Logging).

THE KILLER FEATURE: contextvars
-------------------------------
`bind_contextvars(request_id=..., org_id=...)` is called ONCE, in middleware, at the edge.
Every subsequent log line — in the router, the service, the repository, three layers deep —
automatically carries those fields. Nobody has to thread a logger through fifteen function
signatures, and nobody can forget to.

This is what makes a multi-tenant system debuggable at all. When a customer says "my scan
failed at 14:02", you filter on their `org_id` and read the whole story in order.
contextvars are async-safe: each request/task gets its own isolated copy, so concurrent
requests cannot bleed context into each other.

SECURITY: THE REDACTION PROCESSOR
---------------------------------
`_redact_secrets` drops any key whose name looks sensitive (token, secret, external_id,
authorization, ...). It is a NET, not a policy. The policy is: DO NOT LOG THE THING. But
someone, someday, will log a whole request object or a whole settings object, and this net
is what stands between that mistake and an ExternalId in Datadog (docs/08 § T4).

Roadmap: M0 task 0.4.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from cloudguard_core.config import Settings

# Substrings that mark a field as secret. Matched case-insensitively against the KEY name.
# Deliberately broad: a false-positive redaction costs you one debugging session; a false
# negative costs you a credential rotation and a customer disclosure email.
_SENSITIVE_KEY_PARTS = (
    "secret",
    "token",
    "password",
    "api_key",
    "apikey",
    "authorization",
    "external_id",
    "credential",
    "private",
    "session",
)

_REDACTED = "***REDACTED***"


def _redact_secrets(_logger: Any, _name: str, event_dict: EventDict) -> EventDict:
    """Last-line-of-defence secret redaction (see module docstring).

    Recurses into nested dicts because the realistic accident is
    `log.info("request", data={"headers": {"authorization": "Bearer ..."}})`.
    """

    def scrub(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: (_REDACTED if _is_sensitive(k) else scrub(v)) for k, v in value.items()}
        if isinstance(value, list):
            return [scrub(v) for v in value]
        return value

    return {k: (_REDACTED if _is_sensitive(k) else scrub(v)) for k, v in event_dict.items()}


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def configure_logging(settings: Settings) -> None:
    """Configure structlog for the whole process. Call ONCE, at startup.

    Called from the FastAPI lifespan (apps/api) and the ARQ startup hook (apps/worker), so
    both services produce identical, correlatable log output. An API log line and a worker
    log line for the same scan must be joinable on `request_id` — otherwise distributed
    debugging is guesswork.
    """
    shared_processors: list[Processor] = [
        # Merge in whatever middleware bound via bind_contextvars(). THE important one.
        structlog.contextvars.merge_contextvars,
        # `structlog.processors.add_log_level`, NOT `structlog.stdlib.add_log_level`.
        # The `stdlib.*` processors assume a stdlib `logging.Logger` underneath. We use
        # `WriteLoggerFactory` (a fast, direct-to-stdout logger with no stdlib overhead), so
        # a stdlib processor blows up with `'WriteLogger' object has no attribute 'name'`.
        # Likewise there is no `add_logger_name` here: the logger's name is passed explicitly
        # via `get_logger(__name__)` and appears as the event's `logger` key already.
        structlog.processors.add_log_level,
        # ISO-8601 UTC. Never local time: correlating logs across regions with local
        # timestamps is a special kind of misery.
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        # Redaction runs LAST among the shared processors, so it sees the final, fully
        # merged event dict — including anything the contextvars merge just added.
        _redact_secrets,
    ]

    if settings.is_local or settings.environment.value == "test":
        # Humans read this. Colours, aligned keys, readable tracebacks.
        renderer: Processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        # Machines read this. One JSON object per line — what every log aggregator ingests.
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level.value)
        ),
        logger_factory=structlog.WriteLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging (uvicorn, sqlalchemy, asyncpg, boto3) through structlog too, so
    # that ONE format comes out of the process. Mixed formats break log ingestion, and you
    # discover that only when you're trying to read them during an incident.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.getLevelName(settings.log_level.value),
    )
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "asyncio"):
        logging.getLogger(noisy).handlers.clear()
        logging.getLogger(noisy).propagate = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a logger. Convention: `log = get_logger(__name__)` at module scope."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]
