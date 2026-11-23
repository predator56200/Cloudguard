"""SQLAlchemy ORM models — one file per aggregate.

EMPTY IN M0, AND DELIBERATELY SO.
M0's database deliverable is "configure SQLAlchemy + Alembic; do NOT create application
tables yet." The migration chain is initialised with an empty baseline revision so that the
first REAL migration (M1: organizations, users, memberships) has a parent to build on.

⚠️ CRITICAL, READ BEFORE ADDING YOUR FIRST MODEL:

    Every model module MUST be imported here.

Alembic's autogenerate compares the live database against `Base.metadata`. A model class that
is never imported is never registered on the metadata, so autogenerate cannot see it — and
silently emits an EMPTY migration. You then deploy, and the table isn't there.

That failure is silent, confusing, and everyone hits it exactly once. The explicit import
list below is the cure. Add to it in the same commit as the model.

    # M1
    from cloudguard_core.db.models.organization import Organization
    from cloudguard_core.db.models.user import User
    from cloudguard_core.db.models.membership import Membership
    ...
    __all__ = ["Organization", "User", "Membership", ...]
"""

from __future__ import annotations

__all__: list[str] = []
