"""SQLAlchemy declarative base and shared model mixins.

WHY THE NAMING CONVENTION MATTERS (the most important thing in this file)
------------------------------------------------------------------------
By default, Postgres auto-names constraints and indexes, and SQLAlchemy doesn't know those
names. The consequence surfaces months later, in Alembic:

    op.drop_constraint('???', 'findings')   # what IS it called?

Autogenerate produces migrations it cannot reverse, and `downgrade()` becomes a lie. Since
docs/04 requires EVERY migration to be reversible (and CI tests upgrade→downgrade→upgrade),
a deterministic naming convention is not cosmetic — it is what makes rollback possible.

Set it once, here, before a single table exists. Retrofitting it later means renaming every
constraint in a live database, which is exactly the kind of chore that never gets done.

WHY MIXINS
----------
Every table needs `id`, `created_at`, `updated_at`. Every TENANT table also needs `org_id`.
Writing those four columns 12 times invites the day someone forgets `org_id` on a new table —
and a tenant table without `org_id` cannot have an RLS policy, which means a table with no
tenant isolation at all. `TenantMixin` makes that omission structurally impossible: you cannot
create a tenant model without it.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, MetaData, func

# Alias the SQLAlchemy COLUMN TYPE, not Python's `uuid.UUID`. Two different things share a
# name here, and confusing them produces baffling errors: `PgUUID` is the Postgres column
# type (what the DB stores); `UUID` is the Python value type (what your code holds).
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from cloudguard_core.ids import uuid7

# Deterministic names for every index and constraint Alembic will ever create.
# ix = index, uq = unique, ck = check, fk = foreign key, pk = primary key.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for every ORM model.

    Alembic's `target_metadata` points at `Base.metadata`, which is how autogenerate knows
    what the schema *should* look like. Any model file not imported by the time Alembic runs
    is INVISIBLE to autogenerate — which is why `db/models/__init__.py` imports them all
    explicitly. A forgotten import silently produces an empty migration.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    """A UUIDv7 primary key.

    `default=uuid7` (Python-side), not `server_default=gen_random_uuid()` (Postgres-side).
    Two deliberate reasons:
      1. Postgres has no native UUIDv7 generator yet — only v4, which is exactly the random
         key we rejected in ids.py for destroying B-tree insert locality.
      2. Generating the ID in Python means we KNOW it before the INSERT commits. That lets a
         service build an object graph — and enqueue a job referencing the ID — without a
         round-trip to fetch it back.
    """

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid7)


class TimestampMixin:
    """`created_at` / `updated_at`, both TIMESTAMPTZ (never TIMESTAMP — see clock.py).

    `server_default=func.now()` and `onupdate=func.now()`: the DATABASE stamps these, not the
    application. A row written by a migration, a psql session, or a future Go service still
    gets correct timestamps. Application-set timestamps are always eventually wrong, because
    eventually something other than the application writes a row.

    (Note: this is not a contradiction of clock.py. `created_at` is INFRASTRUCTURE metadata.
    BUSINESS timestamps — `first_seen_at`, `resolved_at`, `expires_at` — are set from the
    injected Clock, because tests must control them.)
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TenantMixin:
    """`org_id` — the tenant discriminator. Layer 2 of four (docs/08 § Tenant isolation).

    Present on EVERY tenant-owned table, even where it is derivable through a join
    (a Finding's org could be reached via cloud_account → organization). Denormalised
    ON PURPOSE:

      1. It is the column RLS policies filter on:
             USING (org_id = current_setting('app.current_org')::uuid)
         A policy cannot traverse a join efficiently — or at all, cheaply.
      2. It is the key we will hash-partition on when `findings` outgrows one table
         ([SCALE-LIMIT], docs/04). That is a migration rather than a rewrite precisely
         BECAUSE every row already carries its tenant.
      3. A join to determine tenancy is a join a developer can forget. A NOT NULL column
         is not.

    ON DELETE CASCADE: deleting an organisation must erase every trace of it in ONE
    statement. GDPR Article 17 is not a feature request.
    """

    org_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
