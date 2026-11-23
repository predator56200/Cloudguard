"""Shared API schemas.

WHY PYDANTIC SCHEMAS AND NOT ORM MODELS ON THE WIRE
---------------------------------------------------
This is not boilerplate. It is a SECURITY BOUNDARY.

`CloudAccount` (the ORM model, M2) has a column called `external_id_encrypted`. If a router
returns the ORM object and lets FastAPI serialise it, that column goes out over the wire the
moment someone adds it — and nobody notices, because no test asserts on the ABSENCE of a
field.

An explicit `CloudAccountRead` schema means a field is exposed only when a human deliberately
types its name. The default is INVISIBLE. When the default is safe, forgetting is safe.

Corollary: the API contract becomes explicit and stable. Renaming a DB column does not
silently rename a public JSON field and break every customer's integration.

M0 ships the generic pieces that every future endpoint reuses.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from cloudguard_core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE


# PEP 695 native generics (`class Foo[T]`), not the legacy `Generic[T]` + `TypeVar` dance.
# Python 3.12+ only, which we are. Less ceremony, and the type parameter is scoped to the
# class rather than leaking as a module-level name.
class CursorPage[T](BaseModel):
    """A page of results, cursor-paginated.

    WHY CURSOR AND NOT OFFSET (docs/05 § Conventions)
    -------------------------------------------------
    `LIMIT 25 OFFSET 50` looks harmless. Now picture the findings table: a scan finishes
    while the user is reading page 3 and inserts 10 new findings at the top. Every row shifts
    down by 10. Page 4 re-shows rows the user already saw on page 3, and silently SKIPS ten
    others. On a security dashboard, "silently skipped ten findings" is not a UX wart — it is
    a customer missing a critical.

    A cursor encodes WHERE YOU WERE ("after last_seen_at=X, id=Y"), so it is stable under
    concurrent inserts. It is also O(1) — offset makes the database count and discard N rows
    on every page, so page 400 is 400× slower than page 1.

    The cursor is opaque (base64) and HMAC-SIGNED (M4). Signing matters: an unsigned cursor is
    just a WHERE clause the client controls, and a client that can craft a WHERE clause can
    try to escape its tenant. Signed → tampering is detected → 422.
    """

    items: list[T]
    next_cursor: str | None = Field(
        default=None, description="Opaque cursor for the next page. null = end of results."
    )
    has_more: bool = Field(
        description="True if more results exist. Prefer this over checking len(items)."
    )


class PaginationParams(BaseModel):
    """Query params every list endpoint accepts.

    `MAX_PAGE_SIZE` is a DoS control, not a nicety: without a cap, `?limit=1000000` makes us
    serialise a million rows into memory on demand, for free, from an unauthenticated-ish
    caller. Bounds on every user-supplied number.
    """

    cursor: str | None = None
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


class ProblemDetail(BaseModel):
    """RFC 7807 error response. Declared here purely so it appears in the OpenAPI schema.

    That matters more than it looks: `make types` generates the frontend's TypeScript from
    this schema, so the frontend's error handling is TYPE-CHECKED against the real contract
    rather than a hand-written guess that drifts.
    """

    type: str = Field(description="Stable, machine-readable error URI. Branch on this.")
    title: str
    status: int
    detail: str
    instance: str | None = None
    request_id: str | None = Field(default=None, description="Quote this in a support ticket.")
    errors: list[dict[str, str]] | None = Field(
        default=None, description="Per-field messages, for 422 only."
    )
