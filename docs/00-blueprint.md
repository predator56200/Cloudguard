# CloudGuard AI — Implementation Blueprint

> Status: **APPROVED ARCHITECTURE — NOT YET IMPLEMENTED**
> Owner: CTO. Last updated: 2026-07-14.
> This directory is the source of truth. Code that contradicts these docs is a bug in the code
> *or* a bug in the docs — either way it gets fixed, never ignored.

## What we are building

**CloudGuard AI — cloud security that fixes itself. Connect AWS + GitHub; we send pull requests, not alerts.**

An AI-powered cloud security platform (CSPM) for startups with 5–100 engineers, AWS
infrastructure, and no dedicated security team.

- **Acquisition:** free, instant, read-only AWS scan → score + top findings.
- **MVP monetisation:** continuous monitoring, prioritised findings, remediation guidance,
  security score trend, weekly email reports.
- **The moat (M9):** the Fix-First remediation engine — map live AWS misconfigurations back to
  the Terraform that created them and open a real pull request.

## Committed decisions (do not relitigate without an ADR)

| Area | Decision |
|---|---|
| Wedge | Fix-first PR engine (M9) + free instant scan (acquisition) |
| Frontend | Next.js 15 (App Router), TypeScript, Tailwind, shadcn/ui, Clerk, TanStack Query |
| Backend | FastAPI, SQLAlchemy 2.0 (async), PostgreSQL, Alembic, ARQ, Redis |
| Infra | Railway (MVP), Docker, GitHub Actions, S3, Resend, Stripe |
| AWS access | Cross-account `sts:AssumeRole` + ExternalId only. `SecurityAudit` + `ViewOnlyAccess`. **No access keys. No write permissions. Ever.** |
| LLM | Claude only. Static rule knowledge authored at build time; per-finding enrichment cached. |
| Tenancy | Shared DB, shared schema, `org_id` everywhere, PostgreSQL Row-Level Security |
| Findings | Fingerprint-based stateful lifecycle (observations reconcile into findings) |
| Transport | REST, `/v1`, cursor-paginated |
| Async | Background workers for everything slow, retryable, or scheduled |

## The scale target

Every decision here is made against one constraint: **10,000 organisations without a rewrite.**
That number is why we chose shared-schema multi-tenancy (not schema-per-tenant), why findings are
reconciled rather than re-inserted, why scans are queued rather than inline, and why the LLM is
called once per finding rather than once per scan.

Where a decision would *not* survive 10,000 orgs, it is called out explicitly as a
**[SCALE-LIMIT]** with the trigger that forces the change and what the change is. There are
exactly five of them in this blueprint. None of them is a rewrite.

## Documents

| # | Doc | Covers |
|---|---|---|
| 01 | [Repository structure](01-repository-structure.md) | Monorepo tree; responsibility of every folder and module |
| 02 | [Backend architecture](02-backend-architecture.md) | Request lifecycle; layering; dependency injection |
| 03 | [Scanner engine](03-scanner-engine.md) | Every abstraction, defined before implementation |
| 04 | [Database](04-database.md) | Every table, relationship, index, migration policy |
| 05 | [API](05-api.md) | Every endpoint, schema, auth, error contract |
| 06 | [Frontend](06-frontend.md) | Routing, layouts, state, component organisation |
| 07 | [Background jobs](07-background-jobs.md) | Queues, scheduling, retries, failure recovery |
| 08 | [Security model](08-security-model.md) | Threat model, isolation, authz, secrets, crypto, audit |
| 09 | [Roadmap](09-roadmap.md) | M0–M9, every task < 1 day |
| 10 | [Testing strategy](10-testing.md) | Unit, integration, E2E, security |
| 11 | [Coding standards](11-coding-standards.md) | Conventions, DI, logging, errors, repositories, config |
| 12 | [Risks](12-risks.md) | Every technical risk + mitigation |

## Reading order for a new engineer

Day 1: 00 → 01 → 02 → 11. Day 2: 04 → 05 → 03. Day 3: 08 → 10. Then pick a task from 09.
