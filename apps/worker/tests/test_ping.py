"""Worker task tests.

Note what this test does NOT do: it does not start Redis, it does not start an ARQ worker,
and it does not enqueue anything.

Because a task is a THIN ADAPTER (tasks/__init__.py), it is just an async function taking a
`ctx` dict. So we call it directly with a fake ctx. No broker, no container, no network —
the test runs in microseconds and belongs in the fast unit suite.

That is the whole argument for keeping tasks thin. When `run_scan` arrives in M4, its logic
will live in `ScanService`, which is tested against a moto-mocked AWS and a real Postgres —
and the TASK will still be a five-line adapter with a test like this one. If a task ever
becomes hard to test, that is the signal that logic has leaked into the wrong layer.
"""

from __future__ import annotations

import pytest

from cloudguard_worker.tasks import ping


@pytest.mark.asyncio
async def test_ping_returns_ok() -> None:
    result = await ping({"job_id": "test-job-1"})
    assert result == {"status": "ok", "message": "pong"}


@pytest.mark.asyncio
async def test_ping_echoes_message() -> None:
    result = await ping({"job_id": "test-job-2"}, message="hello")
    assert result["message"] == "hello"
