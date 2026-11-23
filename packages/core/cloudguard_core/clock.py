"""Time, as an injectable dependency.

WHY THIS FILE EXISTS
--------------------
Because `datetime.now()` is a hidden, un-fakeable, global dependency on the state of the
universe, and it will ruin your test suite.

Concretely, we are about to write rules like:

    "an IAM access key older than 90 days is a HIGH finding"

To test that with `datetime.now()` you must create a key with a hard-coded past date and pray
nobody runs the test near a DST boundary. And to test the *reconciliation* lifecycle
(docs/03) — "first_seen 30 days ago, resolved today, regressed tomorrow" — you literally
cannot, because you cannot make the machine's clock move.

With an injected Clock, you write:

    clock = FrozenClock(datetime(2026, 1, 1, tzinfo=UTC))
    clock.advance(timedelta(days=91))

and the test is deterministic, fast, and readable. A test that calls `datetime.now()` is a
test that fails at midnight on a Tuesday in six months, and nobody will know why.

THE RULE
--------
    Nothing in `packages/core` may call `datetime.now()` or `datetime.utcnow()`.
    Time arrives via `ctx.now` or an injected `Clock`. A ruff rule (DTZ) enforces the
    naive-datetime half of this automatically.

WHY UTC, ALWAYS
---------------
`datetime.now()` returns a NAIVE datetime — no timezone. Compare two naive datetimes from
different machines and you get silent, wrong answers. Every timestamp in this system is
timezone-AWARE UTC, stored in TIMESTAMPTZ columns (docs/04). Localisation happens exactly
once, in the browser.

Roadmap: M0 task 0.6.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    """The time source.

    A Protocol (structural typing), not an ABC (nominal typing): a fake does not have to
    inherit from anything, it just has to have a `now()` method. Less ceremony, same safety —
    mypy checks the shape. This is the pattern for every collaborator in `core`
    (docs/11 § Dependency injection).
    """

    def now(self) -> datetime:
        """Current time, timezone-aware, UTC."""
        ...


class SystemClock:
    """The real clock. Used in production. Injected at the composition root."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    """A controllable clock for tests.

    Not in a `tests/` folder because production code type-hints against `Clock` and test
    helpers that are hard to import get reimplemented badly in five different test files.
    """

    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            # Fail loudly. A naive datetime in a test is the exact bug this class prevents;
            # silently coercing it would defeat the purpose.
            raise ValueError("FrozenClock requires a timezone-aware datetime")
        self._now = start.astimezone(UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        """Move time forward. This is the whole point of the class."""
        self._now += delta

    def set(self, moment: datetime) -> None:
        if moment.tzinfo is None:
            raise ValueError("FrozenClock requires a timezone-aware datetime")
        self._now = moment.astimezone(UTC)
