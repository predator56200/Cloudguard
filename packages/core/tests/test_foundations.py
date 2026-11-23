"""M0 foundation tests.

WHY TEST "TRIVIAL" INFRASTRUCTURE CODE
--------------------------------------
Because these primitives are used by EVERYTHING, so a bug here is a bug everywhere — and
because two of them are security controls whose failure is silent:

  - `_redact_secrets` is the last line of defence against an ExternalId reaching a log
    aggregator (docs/08 § T4). If it silently stops working, nothing breaks, no test goes
    red, no alert fires — we just start leaking credentials into a third-party service.
  - `uuid7` must be genuinely time-ordered or our B-tree insert locality (and the cursor
    pagination that depends on it) quietly degrades.

These run in the "unit" bucket: no DB, no network, no clock. `make test-unit` must stay
under 5 seconds (docs/10) — if the fast suite is slow, engineers stop running it, and then
it may as well not exist.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cloudguard_core.clock import FrozenClock, SystemClock
from cloudguard_core.errors import (
    DomainError,
    NotFoundError,
    PermanentError,
    RetryableError,
)
from cloudguard_core.ids import timestamp_ms_from_uuid7, uuid7
from cloudguard_core.logging import _redact_secrets


class TestUuid7:
    def test_is_version_7(self) -> None:
        assert uuid7().version == 7

    def test_is_time_ordered(self) -> None:
        """The whole reason we chose v7 over v4 (see ids.py).

        Sorting UUIDs must equal sorting by creation time — that is what restores B-tree
        insert locality and lets cursor pagination use the PK as a stable tiebreaker.
        """
        ids = [uuid7() for _ in range(1000)]
        assert ids == sorted(ids)

    def test_is_unique(self) -> None:
        assert len({uuid7() for _ in range(10_000)}) == 10_000

    def test_embeds_a_plausible_timestamp(self) -> None:
        before = int(datetime.now(UTC).timestamp() * 1000)
        ts = timestamp_ms_from_uuid7(uuid7())
        after = int(datetime.now(UTC).timestamp() * 1000)
        assert before - 1000 <= ts <= after + 1000


class TestClock:
    def test_system_clock_is_timezone_aware_utc(self) -> None:
        """A naive datetime is the bug this entire module exists to prevent."""
        assert SystemClock().now().tzinfo is UTC

    def test_frozen_clock_does_not_move(self) -> None:
        clock = FrozenClock(datetime(2026, 1, 1, tzinfo=UTC))
        assert clock.now() == clock.now()

    def test_frozen_clock_advances(self) -> None:
        """This is how we will test '90-day-old access key' rules without waiting 90 days."""
        clock = FrozenClock(datetime(2026, 1, 1, tzinfo=UTC))
        clock.advance(timedelta(days=91))
        assert clock.now() == datetime(2026, 4, 2, tzinfo=UTC)

    def test_frozen_clock_rejects_naive_datetime(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            FrozenClock(datetime(2026, 1, 1))


class TestErrors:
    def test_every_error_is_a_domain_error(self) -> None:
        """Anything NOT descending from DomainError is, by definition, a bug in our code.

        The error handler relies on that distinction to decide between a meaningful status
        and a generic 500 + Sentry alert.
        """
        assert issubclass(NotFoundError, DomainError)
        assert issubclass(RetryableError, DomainError)

    def test_status_codes_are_declared_on_the_class(self) -> None:
        """This is what lets the HTTP error handler avoid an if/elif chain: it just reads
        `exc.status_code`. Adding a new error type needs ZERO changes to the handler."""
        assert NotFoundError.status_code == 404
        assert RetryableError.status_code == 502

    def test_not_found_never_leaks_existence(self) -> None:
        """Cross-tenant access returns 404, not 403 (docs/08 § T1). A 403 would confirm the
        resource exists — an enumeration oracle."""
        exc = NotFoundError("finding", "abc-123")
        assert exc.status_code == 404
        assert "abc-123" not in exc.detail  # the id goes to LOGS, not to the client

    def test_retry_classification_is_encoded_in_the_type(self) -> None:
        """docs/07 § Retries: retrying an AccessDenied wastes our time and looks like an
        attack in the customer's CloudTrail. The decision must live in the TYPE, never in a
        caller's judgement."""
        assert not issubclass(PermanentError, RetryableError)
        assert not issubclass(RetryableError, PermanentError)


class TestSecretRedaction:
    """The net that catches the day someone logs a whole request object (docs/08 § T4)."""

    def test_redacts_sensitive_keys(self) -> None:
        out = _redact_secrets(None, "", {"external_id": "cg_secret", "org_id": "123"})
        assert out["external_id"] == "***REDACTED***"
        assert out["org_id"] == "123"  # non-sensitive fields survive — logs stay useful

    def test_redacts_case_insensitively(self) -> None:
        out = _redact_secrets(None, "", {"Authorization": "Bearer x", "API_KEY": "sk_1"})
        assert out["Authorization"] == "***REDACTED***"
        assert out["API_KEY"] == "***REDACTED***"

    def test_redacts_nested_dicts(self) -> None:
        """The realistic accident: log.info("request", data={"headers": {...}})."""
        out = _redact_secrets(
            None, "", {"request": {"headers": {"authorization": "Bearer leak"}}}
        )
        assert out["request"]["headers"]["authorization"] == "***REDACTED***"

    def test_redacts_inside_lists(self) -> None:
        out = _redact_secrets(None, "", {"accounts": [{"token": "leak", "id": "keep"}]})
        assert out["accounts"][0]["token"] == "***REDACTED***"
        assert out["accounts"][0]["id"] == "keep"
