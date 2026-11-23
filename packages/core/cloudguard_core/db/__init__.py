"""Persistence layer.

Contains:
    base.py          DeclarativeBase + mixins (UUIDv7 PK, timestamps, org_id/RLS)
    session.py       async engine, session factory, RLS-arming session_scope()
    models/          SQLAlchemy ORM models — one file per aggregate (M1+)
    repositories/    THE ONLY place SQL lives. `org_id` is arg #1 of every method. (M1+)

HARD RULE (docs/11 § Repository pattern):
    No SQLAlchemy import may appear OUTSIDE this sub-package.
    A router that imports `select()` has bypassed every guard rail we built.
    Enforced by import-linter in CI.
"""
