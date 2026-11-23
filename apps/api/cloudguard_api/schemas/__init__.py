"""Pydantic request/response schemas — the API's public contract.

THE RULE (docs/05): ORM models NEVER touch the wire.
Every response is an explicit `*Read` schema. That is what keeps `external_id_encrypted` out
of a JSON payload forever — see common.py for the full argument.

Naming convention:
    XCreate   request body for POST
    XUpdate   request body for PATCH (all fields optional)
    XRead     response body (list view — lean)
    XDetail   response body (detail view — includes expensive/joined data)
"""

from cloudguard_api.schemas.common import CursorPage, PaginationParams, ProblemDetail

__all__ = ["CursorPage", "PaginationParams", "ProblemDetail"]
