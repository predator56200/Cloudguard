"""CloudGuard AI — shared domain package.

This package is the heart of the system. It contains everything that is true regardless of
*how* it was invoked: an HTTP request, a background job, a CLI, or a test.

Layering (docs/02-backend-architecture.md) — arrows point down, never up:

    apps/api, apps/worker   (adapters: know FastAPI / ARQ)
              │
              ▼
    core/services           (use cases: know the product)
              │
       ┌──────┼──────┬───────────┐
       ▼      ▼      ▼           ▼
    db/   domain/  scanner/  integrations/

HARD RULE: nothing in this package may import `fastapi` or `arq`.
Enforced by import-linter in CI, because "we'll remember" is not an architecture.
"""

__version__ = "0.1.0"
