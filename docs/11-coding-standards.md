# 11 — Coding Standards

> These are not preferences. They are the rules that let ten engineers touch the same codebase
> without breaking each other. Deviate only with an ADR.

## Python

- **3.12+.** `ruff` (lint + import sort), `black` (format), **`mypy --strict`** on `packages/core`
  and `apps/api`. Untyped code does not merge.
- Type hints on **every** function signature. `from __future__ import annotations` everywhere.
- **`async` all the way down.** No sync DB drivers (`asyncpg`), no `requests` (use `httpx`).
  One blocking call inside an async handler stalls the whole event loop and it is invisible until
  it's a production incident.
- Pydantic v2 for all boundaries (API schemas, config, LLM output parsing).
- Dataclasses (`frozen=True, slots=True`) for domain objects. **Immutable by default** — a `Resource`
  that a rule can mutate is a rule that can corrupt the next rule's input.

## TypeScript

- `strict: true`. **`any` is banned** (`@typescript-eslint/no-explicit-any`: error). `unknown` +
  narrowing is always available and always better.
- No default exports (they make renaming and refactoring silently wrong).
- API types are **generated**, never hand-written.

## Naming

| Thing | Convention | Example |
|---|---|---|
| Python module/function/var | `snake_case` | `finding_service.list_findings` |
| Python class | `PascalCase` | `ScanService` |
| Constants | `UPPER_SNAKE` | `MAX_SCAN_DURATION_S` |
| DB table | plural `snake_case` | `cloud_accounts` |
| DB column | `snake_case`; FKs are `<singular>_id` | `cloud_account_id` |
| Timestamps | **`_at` suffix, always TIMESTAMPTZ** | `resolved_at` |
| Booleans | `is_` / `has_` prefix | `is_default`, `has_mfa` |
| **Rule id** | `snake_case`, `<service>_<subject>_<condition>` | `s3_bucket_public_acl` |
| REST path | plural, kebab | `/v1/cloud-accounts` |
| React component | `PascalCase`, one per file | `FindingsTable.tsx` |
| React hook | `use` prefix | `useFindings` |
| Query key | factory in `lib/query-keys.ts` | `qk.findings(filters)` |
| Job/task | verb-first `snake_case` | `run_scan`, `send_weekly_report` |

**`Rule.id` is permanent public API.** It ends up in the DB, our API, customers' Jira tickets, and
their suppression configs. **Never rename one.** Deprecate and add.

## Dependency injection

**Constructor injection, wired at the edge. No global singletons. No service locator. No magic DI
framework.**

```python
class ScanService:
    def __init__(
        self,
        scans: ScanRepository,
        findings: FindingRepository,
        broker: AwsCredentialBroker,
        engine: RuleEngine,
        clock: Clock,
    ) -> None: ...
```

Every collaborator is a **`Protocol`**, so tests inject fakes and never monkeypatch. `FastAPI`'s
`Depends` and the ARQ context are the **only** two composition roots — they build the objects; the
objects know nothing about them.

Why this matters more than it looks: a `ScanService` that reaches for a module-level `db` or calls
`boto3.client()` internally cannot be tested without the network, cannot be reused by the worker,
and cannot be replaced. **The dependency you didn't inject is the dependency you can't fake, and
the one you can't fake is the one that makes your tests slow and flaky.**

## The repository pattern

**Repositories are the only place SQL exists.** Not "mostly." Only.

```python
class FindingRepository:
    async def get(self, org_id: UUID, finding_id: UUID) -> Finding | None: ...
    async def list(self, org_id: UUID, f: FindingFilters, page: Cursor) -> Page[Finding]: ...
    async def upsert_from_observations(self, org_id: UUID, ...) -> ReconcileResult: ...
```

Rules:
1. **`org_id` is the first positional parameter of every method.** Always. Even when RLS would catch
   it. Belt and braces — and a signature you cannot forget, unlike a `WHERE` clause you can.
2. Repositories return **domain objects or ORM models — never Pydantic schemas.** Serialisation is
   the API layer's job; a repository that knows about HTTP has leaked.
3. **No business logic in a repository.** `list_critical_findings_and_email_them()` is a service.
4. **No SQLAlchemy imports outside `core/db/`.** Enforced by `import-linter`. A router that imports
   `select()` has bypassed every guard rail we built.

## Errors

```
DomainError                     # base — every error we raise
├── ValidationError
├── NotFoundError               # → 404, also used for cross-tenant (never 403)
├── ConflictError               # → 409
├── AuthenticationError         # → 401
├── AuthorizationError          # → 403 (role only, never tenancy)
├── PlanLimitError              # → 402
├── RateLimitError              # → 429
└── IntegrationError            # → 502
    ├── RetryableError          # worker: back off and retry
    └── PermanentError          # worker: dead-letter immediately, do not retry
```

- Services raise **domain** errors. They never raise `HTTPException` — that would couple the domain
  to HTTP and make the same code unusable from the worker.
- **One** exception handler maps domain → RFC 7807. Handlers never format errors.
- **`except: pass` is banned.** So is `except Exception: log.error(...)` followed by returning a
  success. In a scanner, a swallowed exception becomes "score: 100" for a customer who is on fire.
  If you cannot handle it, let it propagate.
- Every raise carries context: `raise NotFoundError("finding", finding_id, org_id=org_id)`.

## Logging

- **`structlog`, JSON in production.** Human-readable in dev.
- **Bind context once, at the edge:** `structlog.contextvars.bind_contextvars(request_id=…,
  org_id=…, user_id=…)`. Every subsequent log line in that request or job carries it for free —
  which is the whole reason you can debug a multi-tenant system at all.
- Levels: `DEBUG` (dev only) · `INFO` (business events: scan started, finding opened) ·
  `WARNING` (degraded: partial scan, LLM failed) · `ERROR` (needs a human).
- **Never log:** tokens, ExternalIds, API keys, request bodies, full AWS responses. A redaction
  processor drops keys matching `/(secret|token|key|password|external_id|authorization)/i` as a
  last line of defence — but the redactor is a net, not a policy. Don't log the thing.
- **Log events, not sentences.** `log.info("scan.completed", scan_id=…, duration_ms=…,
  findings_opened=…)` — queryable. `log.info(f"Scan {id} done in {ms}ms")` — grep-able at best, and
  useless the moment you have 10,000 orgs.

## Configuration

- **All config from the environment** (12-factor). One `Settings` object. `pydantic-settings`.
- **No defaults for secrets.** A missing `ANTHROPIC_API_KEY` must crash the process at boot, in the
  deploy pipeline — not at 3am when the first enrichment job runs.
- No `if ENV == "production"` scattered through the code. Behaviour differences are **injected
  dependencies** (`FakeEmailClient` vs `ResendClient`), chosen once, at the composition root.

## Git & review

- **Conventional Commits** (`feat:`, `fix:`, `chore:`, `sec:`).
- **Small PRs.** A 1,000-line PR gets an "LGTM" and a bug. A 200-line PR gets a review.
- Branch: `feat/M3-s3-collector`, referencing the roadmap task.
- **Every PR answers three questions in its description:** *What changed? How is it tested? What's
  the security impact?* The third one is not optional at a security company.
- New endpoint → an evil-tenant test. New rule → a known-bad + a known-good test. **No exceptions.**

## ADRs

Any decision that would make a new engineer ask "why on earth is it done this way?" gets a numbered
file in `docs/adr/`. Append-only; supersede, never rewrite. **The docs you're reading are ADR-0000.**
