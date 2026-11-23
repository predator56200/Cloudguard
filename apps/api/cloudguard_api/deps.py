"""FastAPI dependencies — the composition root for the HTTP process.

WHAT A "COMPOSITION ROOT" IS, AND WHY IT MATTERS
------------------------------------------------
Somewhere, someone has to actually construct the objects: create the engine, build the
session, wire the repositories into the services. The trick is that this should happen in
EXACTLY ONE PLACE, at the edge, and nowhere else.

This file is that place for the API. `apps/worker/context.py` is that place for the worker.
Between them, they are the only two files in the backend that KNOW how to build a
`ScanService`. Everything else just receives one.

The payoff (docs/11 § Dependency injection):
  - `core` never imports FastAPI. Enforced by import-linter, so the day we add a CLI or an
    MCP server we write a third composition root — not a second copy of the product.
  - A test constructs services directly with fakes. No monkeypatching, no HTTP server, no
    network. That is how the unit suite stays under 5 seconds.

WHY `Annotated[X, Depends(...)]` ALIASES
----------------------------------------
    async def endpoint(db: DbSession) -> ...:

instead of

    async def endpoint(db: AsyncSession = Depends(get_db)) -> ...:

Same behaviour, but the alias is defined ONCE. When `get_db` gains a parameter, we change one
line rather than forty signatures — and mypy still sees the real type.

M0 SCOPE: settings, request-scoped DB session, and the readiness checks. The `Principal`
(who are you, which org, what role) arrives in M1 with Clerk — until then there is no
authenticated endpoint to protect.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cloudguard_core.config import Settings, get_settings
from cloudguard_core.db.session import session_scope

# `Redis` is generic to MYPY (its stubs declare `Redis[str]` vs `Redis[bytes]`) but is NOT
# subscriptable AT RUNTIME. Normally `from __future__ import annotations` makes that
# irrelevant — annotations become strings and are never evaluated. But `Annotated[...]` aliases
# ARE evaluated eagerly, at import time, so `Annotated[Redis[str], ...]` raises
# `TypeError: Redis is not a generic class` and the app will not start.
#
# This split gives mypy the precise type and the interpreter a plain class. It is the standard
# escape hatch for a library whose stubs are more generic than its runtime.
#
# We care about `[str]` specifically because the client is built with `decode_responses=True`
# (main.py): it yields `str`, not `bytes`. Encoding that in the type is what stops someone
# adding a `.decode()` that then blows up at runtime.
if TYPE_CHECKING:
    RedisClient = Redis[str]
else:
    RedisClient = Redis

# --- Configuration ----------------------------------------------------------
# `get_settings` is @lru_cache'd, so this is a singleton per process. Injected rather than
# imported at module scope so a test can override it via `app.dependency_overrides`.
SettingsDep = Annotated[Settings, Depends(get_settings)]


# --- Infrastructure held on app.state ---------------------------------------
# The engine, session factory and Redis pool are created ONCE in the lifespan (main.py) and
# stashed on `app.state`. Creating an engine per request would open a new connection pool per
# request, which exhausts Postgres in about four seconds.


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    """Retrieve the process-wide session factory from app.state."""
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    return factory


def get_redis(request: Request) -> RedisClient:
    """Retrieve the process-wide Redis client from app.state."""
    redis: RedisClient = request.app.state.redis
    return redis


SessionFactoryDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
RedisDep = Annotated[RedisClient, Depends(get_redis)]


# --- Request-scoped database session ----------------------------------------


async def get_db(factory: SessionFactoryDep) -> AsyncIterator[AsyncSession]:
    """One transaction per request. Commits on success, rolls back on any exception.

    ⚠️ NOTE THE `org_id=None` — AND WHY IT IS SAFE TODAY BUT NOT TOMORROW.

    In M0 there is no authentication, therefore no tenant, therefore no RLS context to set.
    That is not a hole: with no `app.current_org` GUC set, `current_setting(..., true)`
    returns NULL, every RLS predicate evaluates to NULL (not TRUE), and every tenant table
    returns ZERO ROWS. **RLS fails closed.** An unset tenant yields an empty result set, not
    a data leak — the correct direction to fail.

    In M1 this becomes:

        async def get_db(factory: SessionFactoryDep, principal: PrincipalDep):
            async with session_scope(factory, org_id=principal.org_id) as session:
                yield session

    ...and from that moment, EVERY query in a request is tenant-scoped by the database itself
    (docs/08 § Tenant isolation, layer 3). There is no privileged path that skips this — no
    admin token, no internal bypass, no service account with global read.
    """
    async with session_scope(factory, org_id=None) as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]
