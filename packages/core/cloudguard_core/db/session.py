"""Database engine and session management.

WHY THIS FILE IS THE MOST SECURITY-CRITICAL FILE IN THE BACKEND
---------------------------------------------------------------
It is where Postgres Row-Level Security is armed. RLS is layer 3 of four in our tenant
isolation model (docs/08) — the layer that catches the bug the other layers miss. It works
like this:

    every tenant table has:
        CREATE POLICY tenant_isolation ON findings
          USING      (org_id = current_setting('app.current_org')::uuid)
          WITH CHECK (org_id = current_setting('app.current_org')::uuid);

    and every transaction begins with:
        SET LOCAL app.current_org = '<the caller's org>';

After that, `SELECT * FROM findings` — with NO WHERE CLAUSE — returns only the current
tenant's rows. The database physically cannot hand back another customer's data, even if a
developer writes a buggy query, even if there is a SQL injection.

THE THREE WAYS TEAMS GET THIS WRONG (all three are guarded here)
----------------------------------------------------------------
1. `SET` instead of `SET LOCAL`.
   `SET` persists for the whole CONNECTION. Connections are POOLED. Request A sets org=A,
   returns the connection to the pool, request B picks it up and inherits org=A.
   **That is a cross-tenant data breach caused by three missing characters.**
   `SET LOCAL` is scoped to the TRANSACTION and is discarded on commit/rollback.

2. Forgetting `FORCE ROW LEVEL SECURITY`.
   The table OWNER bypasses RLS by default. Our app role owns the tables. So plain
   `ENABLE ROW LEVEL SECURITY` does *nothing* for us — you get all the ceremony of RLS and
   none of the protection, and every test passes. (Armed in the M1 migration; noted here
   because this is where you'll come looking.)

3. Forgetting `WITH CHECK`.
   `USING` governs READS. Without `WITH CHECK`, a tenant can INSERT a row with someone
   else's org_id. Read-isolated, write-porous.

WHY A PARAMETERISED `SET LOCAL` IS NOT POSSIBLE
-----------------------------------------------
Postgres does not accept bind parameters in `SET`. So we interpolate — which means we MUST
prove the value is a UUID first. `session_scope()` takes a `uuid.UUID` object (not a string),
and we re-serialise it via `str(uuid_obj)`. A UUID cannot contain a quote, so injection is
structurally impossible. This is the one place in the codebase where string interpolation
into SQL is acceptable, and it is safe only because of the type.

Roadmap: M0 task 0.5 (engine); RLS policies arrive with the first tenant table in M1.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from cloudguard_core.config import Settings
from cloudguard_core.logging import get_logger

log = get_logger(__name__)

# The Postgres GUC (Grand Unified Configuration) parameter our RLS policies read.
# Custom GUCs must contain a dot — that's how Postgres distinguishes them from built-ins.
TENANT_GUC = "app.current_org"


def create_engine(settings: Settings) -> AsyncEngine:
    """Build the async engine. ONE per process, created at startup.

    Pooling notes:
      - `pool_pre_ping=True`: Postgres (and, more often, the cloud provider's proxy in front
        of it) silently closes idle connections. Without pre-ping, the first query after an
        idle period fails with a baffling "server closed the connection unexpectedly". The
        cost is one trivial round-trip per checkout. Always worth it.
      - `pool_recycle=1800`: proactively drop connections older than 30 min, for the same
        reason.
      - Pool size is per PROCESS. Total connections = pool_size × api_replicas +
        pool_size × worker_replicas. Postgres has a hard `max_connections` (~100 by default),
        so this is a number to watch as we scale horizontally. [SCALE-LIMIT: introduce
        PgBouncer in transaction-pooling mode when replicas × pool_size approaches it. Note
        that transaction pooling is COMPATIBLE with our SET LOCAL approach precisely because
        the setting is transaction-scoped — another dividend of getting #1 above right.]
    """
    return create_async_engine(
        str(settings.database_url),
        echo=settings.database_echo,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build the session factory.

    `expire_on_commit=False`: by default SQLAlchemy expires every object after commit, so
    touching any attribute afterwards triggers a fresh SELECT — which in async code raises
    a confusing `MissingGreenlet` error rather than just being slow. We commit and then
    serialise the object to JSON constantly, so this default is actively hostile to us.
    """
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,  # be explicit about when SQL is emitted
    )


@asynccontextmanager
async def session_scope(
    factory: async_sessionmaker[AsyncSession],
    org_id: UUID | None = None,
) -> AsyncIterator[AsyncSession]:
    """Open a transaction, arm RLS for `org_id`, commit on success, roll back on error.

    This is THE way to get a database session. Both the API (via a FastAPI dependency) and
    the worker (via its task context) go through it, so there is exactly one code path that
    sets the tenant, and therefore exactly one place to audit. There is NO privileged
    "internal" path that skips RLS — no admin bypass, no service account with global read.

    Args:
        org_id: The tenant. `None` is permitted ONLY for genuinely global work: migrations,
            health checks, and reads of the global `rules` catalogue. It is NOT a back door —
            with no GUC set, `current_setting('app.current_org', true)` returns NULL, the RLS
            predicate evaluates to NULL (not TRUE), and every tenant table returns ZERO rows.
            **RLS fails CLOSED.** An accidental `org_id=None` yields an empty result set, not
            a data leak. That is the correct direction to fail.
    """
    async with factory() as session:
        try:
            if org_id is not None:
                # Safe interpolation: `org_id` is a typed uuid.UUID, so `str()` can only
                # produce 36 hex-and-dash characters. See the module docstring.
                await session.execute(text(f"SET LOCAL {TENANT_GUC} = '{org_id!s}'"))
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        # `async with factory()` closes the session (returning the connection to the pool)
        # on the way out, whether we succeeded or not.


async def check_database(factory: async_sessionmaker[AsyncSession]) -> bool:
    """Liveness probe for the DB. Used by /readyz (never by /healthz — see routers/health.py)."""
    try:
        async with factory() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001 — a readiness probe must never itself crash
        log.warning("readiness.database_unavailable", error=str(exc))
        return False
