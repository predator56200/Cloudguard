# @cloudguard/ts-types

**Generated. Never hand-edited.** Wired up in M5 (roadmap task 5.1).

## What this is

`api.d.ts` is TypeScript generated from the backend's OpenAPI schema:

```
make types
  → GET http://localhost:8000/openapi.json      (FastAPI generates this from our Pydantic schemas)
  → openapi-typescript
  → packages/ts-types/api.d.ts                   (committed to git)
```

## Why it exists

**The backend is the single source of truth for the API contract, and the frontend cannot drift
from it without CI failing.**

That sentence is the whole point. The most common bug class in split-stack teams is the frontend
and the backend quietly disagreeing about the shape of a response — a renamed field, a nullable
that became non-nullable, an enum that gained a value. Nothing crashes at build time; a user finds
it for you, in production, and it presents as "the dashboard is blank".

With generated types:

- A component **cannot** reference a field the API does not return. `tsc` fails.
- A backend engineer who renames `effective_severity` finds out **in CI**, not from a customer.
- CI regenerates this file and **fails if the committed version differs** — so it can never go
  stale without someone noticing.

This is why `strict: true` and the ban on `any` are non-negotiable in the frontend
(`apps/web/eslint.config.mjs`): one `any` at the fetch boundary and this entire guarantee
silently evaporates. The types become decoration, and we are back to hoping.

## Why it's committed to git rather than generated at install

So that `git clone && npm install && npm run dev` works without a running backend. A new engineer
should not need Docker up and Postgres migrated just to typecheck a CSS change.
