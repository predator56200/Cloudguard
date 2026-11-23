"""Pytest fixtures for the API.

WHAT `dependency_overrides` BUYS US, AND WHY IT'S THE PAYOFF FOR ALL THAT DI CEREMONY
-------------------------------------------------------------------------------------
The health endpoints depend on a real Postgres and a real Redis. But testing that
`/healthz` returns 200 should NOT require a database — that test is about the HTTP layer, and
it must run in the sub-5-second unit suite (docs/10).

Because every dependency is INJECTED (deps.py) rather than imported at module scope, a test
can swap in a fake with two lines and no monkeypatching:

    app.dependency_overrides[get_redis] = lambda: FakeRedis()

Monkeypatching `redis.asyncio.Redis.ping` would couple this test to a third-party library's
internals; it would break when they refactor, with an error message that tells you nothing.
Overriding OUR interface couples the test to a contract WE control.

This is the concrete, cash-value reason for the dependency-injection rules in docs/11. It is
not architecture astronomy — it is the difference between a 5-second test suite and a
5-minute one, and a 5-minute suite is a suite nobody runs.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cloudguard_api.deps import get_redis, get_session_factory
from cloudguard_api.main import create_app
from cloudguard_core.config import Environment, Settings


@pytest.fixture
def settings() -> Settings:
    """Test settings.

    The DSNs must be SHAPED correctly (Pydantic validates them at construction) but need not
    point at anything real — every test that would touch them overrides the dependency.
    """
    return Settings(
        environment=Environment.TEST,
        database_url="postgresql+asyncpg://test:test@localhost:5432/test",
        redis_url="redis://localhost:6379/1",
        cors_origins=["http://localhost:3000"],
    )


class FakeRedis:
    """A Redis test double.

    `healthy=False` lets us test the FAILURE path of /readyz — which is the path that
    actually matters. A readiness probe that has only ever been tested when everything works
    is a readiness probe you are trusting on faith.
    """

    def __init__(self, *, healthy: bool = True) -> None:
        self.healthy = healthy

    async def ping(self) -> bool:
        if not self.healthy:
            raise ConnectionError("redis is down")
        return True


class FakeSessionFactory:
    """A SQLAlchemy session-factory double.

    `check_database()` calls `factory()` as an async context manager and runs `SELECT 1`.
    We mimic just enough of that shape — no more. A test double should implement the
    interface under test, not the whole library.
    """

    def __init__(self, *, healthy: bool = True) -> None:
        self.healthy = healthy

    def __call__(self) -> FakeSessionFactory:
        return self

    async def __aenter__(self) -> FakeSessionFactory:
        if not self.healthy:
            raise ConnectionError("database is down")
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def execute(self, *args: object, **kwargs: object) -> None:
        if not self.healthy:
            raise ConnectionError("database is down")


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    """A fresh app per test.

    This is why `create_app()` is a FACTORY and not a module-level global (see main.py):
    tests get isolated instances, and one test's dependency_overrides cannot bleed into the
    next one's.

    ⚠️ NOTE WHAT WE DO *NOT* DO HERE: we do not seed `app.state.redis` / `.session_factory`.
    That was the obvious approach and it is WRONG, in a way worth recording because it will
    bite the next person too:

        `with TestClient(app)` RUNS THE LIFESPAN. The lifespan (main.py) builds the real
        engine and the real Redis client and assigns them to `app.state` — clobbering
        anything a fixture put there, and pointing the "healthy" test at a Postgres that
        isn't running.

    So we override the DEPENDENCIES instead. `get_session_factory`/`get_redis` are the seam
    (deps.py); overriding them means the lifespan can build whatever it likes and no endpoint
    will ever ask for it. Lazily-constructed objects that are never used open no sockets, so
    this stays hermetic.

    This is precisely the payoff of routing everything through a dependency rather than
    reaching for a global: there is a seam to grab.
    """
    application = create_app(settings=settings)
    application.dependency_overrides[get_session_factory] = lambda: FakeSessionFactory()
    application.dependency_overrides[get_redis] = lambda: FakeRedis()
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def unhealthy_client(app: FastAPI) -> Iterator[TestClient]:
    """A client whose dependencies are DOWN. For testing /readyz's failure path — which is
    the path that actually matters. A readiness probe that has only ever been exercised when
    everything works is a probe you are trusting on faith."""
    app.dependency_overrides[get_redis] = lambda: FakeRedis(healthy=False)
    app.dependency_overrides[get_session_factory] = lambda: FakeSessionFactory(healthy=False)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
