"""Repositories — the ONLY place SQL exists.

Empty in M0 (no tables yet). The generic `Repository[T]` base arrives in M1 (task 1.6).

THE FOUR RULES (docs/11 § Repository pattern) — read these before writing the first one:

1. `org_id` is the FIRST POSITIONAL PARAMETER of every method. Always. Even though RLS would
   catch a mistake, this is layer 2 of four (docs/08). A parameter you cannot omit without a
   TypeError is strictly better than a WHERE clause you can forget.

       async def get(self, org_id: UUID, finding_id: UUID) -> Finding | None: ...

2. Repositories return DOMAIN OBJECTS or ORM MODELS — never Pydantic response schemas.
   Serialisation is the API layer's job. A repository that knows about HTTP has leaked.

3. NO BUSINESS LOGIC. `list_critical_findings_and_email_them()` is a service, not a repo.
   A repository answers "what is in the database"; a service decides what to do about it.

4. NO SQLAlchemy outside this sub-package. Enforced by import-linter.
"""

from __future__ import annotations

__all__: list[str] = []
