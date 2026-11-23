# 01 — Repository Structure

## Why a monorepo

Three deployable units (web, api, worker) share one domain vocabulary: a `Finding` on the
dashboard must mean exactly what a `Finding` means in the scanner. In a polyrepo, that shared
vocabulary drifts within weeks and you discover it in production. A monorepo gives us:

- **One atomic commit** for a change that spans API + types + UI. No coordinated-deploy dance.
- **One CI pipeline** that can prove a backend schema change didn't break the frontend.
- **Generated types**: the frontend's TypeScript types are generated from FastAPI's OpenAPI
  schema. The backend is the single source of truth for the API contract; the frontend cannot
  drift from it without CI failing.

We do **not** use Nx/Turborepo/Bazel. Two languages, three apps — a Makefile and Docker Compose
are sufficient and cost zero learning time. Revisit only if build times exceed ~5 minutes.

## Tree

```
cloudguard/
├── README.md
├── Makefile                          # the ONLY interface developers memorise
├── docker-compose.yml                # local: postgres, redis, api, worker, web
├── docker-compose.test.yml           # ephemeral services for integration tests
├── .env.example                      # every var, documented, no real secrets
├── .editorconfig
├── .gitignore
├── .pre-commit-config.yaml           # ruff, black, mypy, eslint, gitleaks
│
├── docs/                             # THIS BLUEPRINT — source of truth
│   ├── 00-blueprint.md … 12-risks.md
│   └── adr/                          # Architecture Decision Records, append-only
│       └── 0001-shared-schema-multitenancy.md
│
├── .github/
│   └── workflows/
│       ├── ci.yml                    # lint → typecheck → unit → integration → build
│       ├── security.yml              # gitleaks, pip-audit, npm audit, trivy, CodeQL
│       ├── e2e.yml                   # Playwright against ephemeral stack
│       └── deploy.yml                # Railway deploy on main, gated on ci+security
│
├── infra/
│   ├── cloudformation/
│   │   └── cloudguard-role.yml       # THE artefact customers run. Reviewed like prod code.
│   ├── terraform/                    # OUR own AWS (S3 buckets, KMS key, scanner IAM user)
│   └── railway/
│       └── railway.json
│
├── apps/
│   ├── api/                          # FastAPI HTTP service  (stateless, fast, no slow work)
│   ├── worker/                       # ARQ worker            (slow, retryable, scheduled work)
│   └── web/                          # Next.js 15            (dashboard + marketing + free scan)
│
└── packages/
    ├── core/                         # THE domain. Shared by api + worker. Knows no HTTP, no queue.
    └── ts-types/                     # OpenAPI-generated TS types. Never hand-edited.
```

> **Note on `packages/core`:** this is the single most important structural decision in the repo.
> Read §"The core package" below before writing a line of code.

---

## `packages/core` — the domain package

```
packages/core/cloudguard_core/
├── __init__.py
├── config.py                  # pydantic-settings; ALL env vars; fails fast on boot
├── logging.py                 # structlog config; JSON in prod, pretty in dev; org_id binding
├── errors.py                  # the exception hierarchy (see 11-coding-standards)
├── clock.py                   # Clock protocol + SystemClock/FrozenClock. NEVER call datetime.now()
├── ids.py                     # UUIDv7 generation (time-sortable primary keys)
│
├── db/
│   ├── base.py                # DeclarativeBase, naming convention for constraints
│   ├── session.py             # async engine, sessionmaker, TenantSession (sets RLS GUC)
│   ├── models/                # SQLAlchemy ORM models, one file per aggregate
│   │   ├── organization.py  user.py  cloud_account.py  scan.py  resource.py
│   │   ├── rule.py  finding.py  finding_event.py  suppression.py
│   │   ├── score_snapshot.py  remediation.py  api_key.py  audit_log.py
│   └── repositories/          # THE ONLY place raw queries live. org_id is arg #1, always.
│       ├── base.py            # Repository[T] generic: get, list, create, update
│       ├── cloud_accounts.py  scans.py  findings.py  resources.py
│       ├── scores.py  suppressions.py  audit.py
│
├── domain/                    # Pure Python. No I/O. No SQLAlchemy. 100% unit-testable.
│   ├── severity.py            # Severity enum + effective-severity calculation
│   ├── fingerprint.py         # the finding identity function
│   ├── scoring.py             # security score algorithm
│   └── lifecycle.py           # observation → finding reconciliation state machine
│
├── scanner/                   # see 03-scanner-engine.md
│   ├── engine.py  registry.py  collectors/  rules/  models.py  aws.py
│
├── services/                  # USE CASES. Orchestrate repos + scanner + integrations.
│   ├── cloud_account_service.py   # onboarding, AssumeRole verification
│   ├── scan_service.py            # run a scan end-to-end, reconcile, snapshot score
│   ├── finding_service.py         # suppress, resolve, list with filters
│   ├── enrichment_service.py      # Claude per-finding context (cached)
│   ├── report_service.py          # weekly report: render → PDF → S3 → Resend
│   └── billing_service.py         # Stripe: plans, limits, entitlements
│
├── integrations/              # THIN wrappers over the outside world. Each behind a Protocol.
│   ├── llm/                   # LLMClient protocol; AnthropicClient; FakeLLMClient (tests)
│   ├── email/                 # EmailClient protocol; ResendClient; FakeEmailClient
│   ├── storage/               # ObjectStore protocol; S3Store; InMemoryStore
│   ├── billing/               # Stripe
│   ├── github/                # M9 only. GitHub App, PR creation.
│   └── clerk/                 # JWT verification, webhook signature verification
│
├── content/                   # STATIC RULE KNOWLEDGE. Authored once. Cost $0 at runtime.
│   └── rules/
│       └── s3_bucket_public_acl.md   # frontmatter: id, severity, refs
│                                     # body: explanation, business impact, fix, CLI, Terraform
└── tests/                     # unit tests for the domain + scanner (moto), no network
```

### The core package: responsibility

`packages/core` contains **everything that is true regardless of how it was invoked.** A public S3
bucket is critical whether the scan was triggered by an HTTP request, a cron job, or a test. So the
rule that says so lives in `core`, not in `api` and not in `worker`.

The consequence, which you must internalise:

- `apps/api` is a **thin HTTP adapter** over `core.services`. It parses, authorises, calls a
  service, serialises. If an endpoint contains business logic, it's in the wrong layer.
- `apps/worker` is a **thin queue adapter** over `core.services`. Same rule.
- **A use case must be callable from both, with no code duplication and no import of `fastapi`
  or `arq` inside `core`.** If `core` ever imports FastAPI, the layering is broken.

This is what makes the codebase survive to 10,000 orgs: the day we add a CLI, a GraphQL gateway,
or an MCP server, we write another 200-line adapter — we do not reimplement the product.

### `content/rules` — why static markdown, not the LLM

Findings originate from a **finite catalogue of ~30 rules**. The technical explanation, business
impact, remediation steps, AWS CLI command, and Terraform snippet for "S3 bucket has a public ACL"
are *identical for every customer, forever*. Generating them at runtime with an LLM would mean
paying per token, for non-deterministic output, that we cannot review.

So: they are **authored once, reviewed by a human, committed as markdown, seeded into the `rules`
table by migration.** Runtime LLM usage is restricted to the genuinely per-resource part
(`findings.ai_context_md`), generated once per finding and cached. This is the difference between
85% gross margin and 40%. See [03](03-scanner-engine.md) §Rule content.

---

## `apps/api` — FastAPI HTTP service

```
apps/api/
├── Dockerfile
├── pyproject.toml
└── cloudguard_api/
    ├── main.py                  # app factory; middleware; router mounting; lifespan
    ├── deps.py                  # FastAPI dependencies: db session, principal, org, entitlements
    ├── middleware/
    │   ├── request_id.py         # X-Request-ID in, bound to logs, echoed out
    │   ├── logging.py            # structured access log; never logs bodies or tokens
    │   ├── rate_limit.py         # Redis token bucket, per-org
    │   └── error_handler.py      # exception → RFC 7807 problem+json. The ONLY place we format errors.
    ├── security/
    │   ├── clerk_jwt.py          # JWKS fetch + cache, verify, extract org_id/user_id/role
    │   ├── api_key.py            # hashed API-key auth (machine clients)
    │   └── principal.py          # Principal = who you are + which org + what role
    ├── schemas/                  # Pydantic REQUEST/RESPONSE models. Never ORM models on the wire.
    │   ├── common.py             # CursorPage[T], ProblemDetail, IdempotencyKey
    │   ├── cloud_account.py  scan.py  finding.py  score.py  billing.py
    └── routers/
        ├── health.py             # /healthz (liveness), /readyz (db+redis)
        ├── cloud_accounts.py  scans.py  findings.py  score.py  rules.py
        ├── billing.py  public_scan.py       # public_scan = the free-scan acquisition loop
        └── webhooks/  stripe.py  clerk.py
```

**Responsibility:** authenticate, authorise, validate, delegate, serialise. Nothing else.
**Hard rule:** an API request never does slow work. Anything that touches customer AWS, the LLM,
S3, or email is enqueued and returns `202 Accepted`. A dashboard must never be slow because a
customer's AWS account is.

## `apps/worker` — ARQ worker

```
apps/worker/
├── Dockerfile
└── cloudguard_worker/
    ├── main.py                  # ARQ WorkerSettings: queues, concurrency, lifespan, cron
    ├── context.py               # builds the same service objects the API builds
    ├── tasks/
    │   ├── scan.py              # run_scan(org_id, cloud_account_id, scan_id)
    │   ├── enrich.py            # enrich_finding(finding_id)  ← Claude, cached
    │   ├── report.py            # send_weekly_report(org_id)
    │   ├── snapshot.py          # capture_daily_scores()
    │   └── remediation.py       # M9: open_fix_pr(finding_id)
    └── schedules.py             # cron definitions (see 07-background-jobs.md)
```

**Responsibility:** execute long, retryable, scheduled work. Owns all egress to customer AWS.
**Hard rule:** a task is a thin call into a `core.service`, plus retry/idempotency handling.

## `apps/web` — Next.js 15

```
apps/web/
├── app/
│   ├── (marketing)/             # public: landing, pricing, free scan, trust page
│   ├── (auth)/                  # Clerk sign-in / sign-up
│   ├── (dashboard)/             # authenticated app; layout enforces org selection
│   │   ├── layout.tsx  page.tsx (overview)
│   │   ├── findings/  cloud-accounts/  reports/  settings/
│   └── api/                     # Route Handlers: BFF proxy only (attach Clerk token, hide API URL)
├── components/
│   ├── ui/                      # shadcn primitives. Generated. Not hand-edited.
│   ├── findings/  dashboard/  onboarding/  layout/
├── lib/
│   ├── api-client.ts            # typed fetch wrapper over packages/ts-types
│   ├── query-keys.ts            # centralised TanStack Query key factory
│   └── utils.ts
├── hooks/                       # useFindings, useScore, useCloudAccounts (TanStack Query)
└── e2e/                         # Playwright
```

See [06-frontend.md](06-frontend.md).

## `packages/ts-types`

`make types` runs: API → `/openapi.json` → `openapi-typescript` → `packages/ts-types/api.d.ts`.
Committed to git. **CI regenerates and fails if the committed file differs.** This is how a
backend engineer physically cannot break the frontend contract without knowing.

## The Makefile is the developer interface

```
make dev          # docker compose up: postgres, redis, api, worker, web
make migrate      # alembic upgrade head
make migration m="add findings table"
make test         # unit + integration
make test-security# the evil-tenant suite (see 10-testing.md)
make lint         # ruff + black + mypy + eslint + tsc
make types        # regenerate packages/ts-types from OpenAPI
make seed         # load rule catalogue + a demo org with fake findings
```

New engineer, day one: `git clone && cp .env.example .env && make dev && make seed`. If that
doesn't produce a working dashboard in under 10 minutes, that is a P1 bug and we fix it before
we ship features.
