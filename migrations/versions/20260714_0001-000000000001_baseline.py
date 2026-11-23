"""baseline — empty schema

Revision ID: 000000000001
Revises:
Created: 2026-07-14

------------------------------------------------------------------------------
WHY AN EMPTY MIGRATION EXISTS
------------------------------------------------------------------------------
M0's database deliverable is explicit: "Configure SQLAlchemy, Alembic and the PostgreSQL
connection. Do NOT create application tables yet. Only initialise migrations."

So this revision creates nothing. Its job is to be a ROOT — a parent for the first real
migration (M1: organizations, users, memberships) to chain from — and to prove, today, that
the whole migration machinery actually works end to end:

    docker compose exec api alembic upgrade head    → creates alembic_version, stamps 0001
    docker compose exec api alembic downgrade base  → unwinds cleanly

Discovering that Alembic cannot reach the database is a five-minute fix now. Discovering it
in M1, tangled up with a broken RLS policy and a model you're also debugging, is an afternoon.
Prove the machinery in isolation, before it has anything to hide behind.

WHAT IT DOES DO
---------------
Enables `pgcrypto`. We use Python-side UUIDv7 for primary keys (core/ids.py explains why: v4
is random, destroys B-tree insert locality, and Postgres has no native v7 generator). But
`gen_random_uuid()` and `digest()` are useful for data migrations and for `DEFAULT`s on tables
written by something other than our app. `CREATE EXTENSION` requires elevated privileges, and
a migration is the correct — and only — place we hold them.
------------------------------------------------------------------------------
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "000000000001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # IF NOT EXISTS: this migration must be re-runnable against a database where a previous
    # partial run already created it. Idempotent migrations are kinder to your future self.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # No tables. See the module docstring — this is deliberate, not an omission.
    #
    # M1 (task 1.3) adds the reusable RLS helper that every subsequent tenant table calls:
    #
    #     def enable_rls(table: str) -> None:
    #         op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    #         op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    #         op.execute(f'''
    #             CREATE POLICY tenant_isolation ON {table}
    #               USING      (org_id = current_setting('app.current_org', true)::uuid)
    #               WITH CHECK (org_id = current_setting('app.current_org', true)::uuid)
    #         ''')
    #
    # Writing that helper ONCE — rather than hand-rolling three statements per table across
    # a dozen migrations — is what stops the twelfth table from being the one where someone
    # forgets `FORCE` and silently ships a table with no tenant isolation at all.


def downgrade() -> None:
    # Deliberately NOT dropping pgcrypto: other objects may come to depend on it, and a
    # downgrade that breaks the database is worse than a downgrade that leaves an unused
    # extension behind. Reversibility means "safely undo", not "erase all evidence".
    pass
