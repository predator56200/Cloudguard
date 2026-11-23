# CloudGuard AI

**Cloud security that fixes itself. Connect AWS + GitHub; we send pull requests, not alerts.**

AI-powered AWS security posture management for startups with 5–100 engineers, AWS infrastructure,
and no dedicated security team.

> **Status: M0 — Foundations.** The skeleton is complete and deployable. There is no business
> logic yet, and that is deliberate. See [docs/09-roadmap.md](docs/09-roadmap.md).

## About this project

CloudGuard is a startup idea I'm building as a solo student project. It connects my Computer Forensics and Telecommunication Engineering coursework with my Using Technology in Entrepreneurship class. The idea: small startups run on AWS but rarely have a security team, so mistakes like a public S3 bucket go unnoticed. CloudGuard would find those problems and open a pull request that fixes them, instead of just sending another alert.

**Where it stands right now:** I've finished the foundations (milestone M0). That means the architecture, the API, the background worker, the database migrations, the dashboard shell, CI, and 29 passing tests. The security scanning itself starts in later milestones, and the dashboard pages show which milestone each feature arrives in. I wrote the design docs in [`docs/`](docs/00-blueprint.md) as if for a real engineering team, because I wanted to practice planning a product the way a startup would.

**What I learned building the foundations:**
- Structuring a monorepo so the core logic doesn't depend on the web framework or the job queue, and enforcing that automatically in CI
- Designing for multi-tenant security from day one, since one customer must never see another's data
- Setting up a professional workflow: Docker, migrations, linting, type checking, pre-commit hooks, and GitHub Actions
- Writing a roadmap that breaks a large product into tasks of less than a day each

---

## Quick start

**Prerequisites:** Docker Desktop, and that's it. No local Python, no local Node, no local Postgres.

```bash
git clone https://github.com/predator56200/cloudguard.git && cd cloudguard
cp .env.example .env          # local defaults work as-is; no real secrets needed for M0
make dev                      # Windows:  .\make.ps1 dev
```

Then, in a second terminal:

```bash
make migrate                  # Windows:  .\make.ps1 migrate
```

| Service | URL |
|---|---|
| Web (dashboard) | http://localhost:3000 |
| Web (landing) | http://localhost:3000/ |
| API docs | http://localhost:8000/docs |
| API liveness | http://localhost:8000/healthz |
| API readiness | http://localhost:8000/readyz |
| Postgres | `localhost:5432` — `cloudguard` / `cloudguard` |
| Redis | `localhost:6379` |

**If that does not produce a working dashboard in under 10 minutes on a clean machine, that is a
P1 bug and we fix it before we ship features.** A new engineer's first hour should be spent reading
code, not installing databases.

---

## Commands

Everything goes through `make` (or `.\make.ps1` on Windows — the two files mirror each other and
must stay in sync).

| Command | What it does |
|---|---|
| `make dev` | Start the full stack: postgres, redis, api, worker, web |
| `make down` | Stop it (data preserved) |
| `make clean` | Stop it and **destroy all data** |
| `make logs` | Tail all logs |
| `make shell` | Shell into the api container |
| `make migrate` | Apply pending migrations |
| `make migration m="add findings"` | Create a new migration |
| `make test` | All backend tests |
| `make test-unit` | Fast tests only — no DB, no network, **under 5 seconds** |
| `make lint` | Ruff + Black + ESLint |
| `make fmt` | Auto-format everything |
| `make typecheck` | mypy `--strict` + `tsc` |

---

## Repository layout

```
cloudguard/
├── docs/           ⭐ THE SOURCE OF TRUTH. Read 00-blueprint.md first.
├── apps/
│   ├── api/        FastAPI. Stateless HTTP adapter. Never does slow work.
│   ├── worker/     ARQ. Slow, retryable, scheduled work. Owns all AWS egress.
│   └── web/        Next.js 15 dashboard + marketing + free-scan funnel.
├── packages/
│   ├── core/       ⭐ THE DOMAIN. Shared by api + worker. Knows no HTTP, no queue.
│   └── ts-types/   Generated TS types from the API's OpenAPI schema. Never hand-edited.
├── infra/          CloudFormation (what customers run), Terraform (our own AWS), Railway.
└── migrations/     Alembic. Every schema change. No exceptions.
```

### The one structural idea that matters

**`packages/core` contains everything that is true regardless of how it was invoked.**

A public S3 bucket is critical whether the scan was triggered by an HTTP request, a cron job, or a
test. So the rule that says so lives in `core` — not in the API, not in the worker.

Consequently:

- `apps/api` is a **thin HTTP adapter** over `core.services`.
- `apps/worker` is a **thin queue adapter** over `core.services`.
- **Nothing in `core` may import `fastapi` or `arq`.** This is enforced by `import-linter` in CI
  (`.importlinter`) — it is a build failure, not a code-review opinion.

That rule is why the same scan logic can be triggered by an HTTP request, a cron job, or a test with
zero duplication, and why adding a CLI or an MCP server later is a 200-line adapter rather than a
rewrite.

---

## Architecture

The full blueprint lives in [`docs/`](docs/00-blueprint.md). Start there — it is written for someone
joining the team, and it explains *why*, not just *what*.

| Doc | Covers |
|---|---|
| [00-blueprint](docs/00-blueprint.md) | Index + committed decisions |
| [01-repository-structure](docs/01-repository-structure.md) | Every folder's responsibility |
| [02-backend-architecture](docs/02-backend-architecture.md) | How a request moves through the system |
| [03-scanner-engine](docs/03-scanner-engine.md) | Collectors, Rules, Observations, Findings |
| [04-database](docs/04-database.md) | Tables, relationships, indexes, RLS, migrations |
| [05-api](docs/05-api.md) | Endpoints, schemas, auth, RFC 7807 errors |
| [06-frontend](docs/06-frontend.md) | Routing, state, components |
| [07-background-jobs](docs/07-background-jobs.md) | Queues, cron, retries, failure recovery |
| [08-security-model](docs/08-security-model.md) | ⭐ **Read before your first commit.** |
| [09-roadmap](docs/09-roadmap.md) | M0–M9, every task under one day |
| [10-testing](docs/10-testing.md) | Unit, integration, E2E, security |
| [11-coding-standards](docs/11-coding-standards.md) | Conventions, DI, repositories, logging |
| [12-risks](docs/12-risks.md) | Every technical risk + mitigation |

### The five things a new engineer must internalise

1. **Tenant isolation has four independent layers** (org-scoped Principal → `org_id` as argument #1
   of every repository method → Postgres RLS → the evil-tenant test suite). One bug here leaks one
   customer's vulnerabilities to another, which for a security vendor is not an incident — it is the
   end. Four layers is the correct amount of paranoia.

2. **We never accept AWS access keys.** Cross-account `AssumeRole` with a per-tenant ExternalId
   *that we generate*, `SecurityAudit` + `ViewOnlyAccess`, zero write permissions. We are
   *structurally incapable* of modifying a customer's cloud.

3. **Findings are stateful**, identified by `fingerprint = sha256(account|rule|arn)`. Scans emit
   *observations*; a pure function reconciles them into findings. Duplicates are impossible by
   database constraint.

4. **A scan that fails must never auto-resolve findings.** Broken credentials → no observations →
   naive code marks everything resolved → the customer sees "score 100, zero findings" while their
   cloud is on fire. This is the most dangerous bug our architecture permits
   ([docs/12 § R3](docs/12-risks.md)). It has a dedicated test that never gets deleted.

5. **`except: pass` is banned.** In a security scanner, a swallowed exception becomes "all clear".

---

## Tech stack

**Frontend** Next.js 15 · TypeScript (strict) · Tailwind v4 · shadcn/ui · TanStack Query · Clerk (M1)
**Backend** FastAPI · SQLAlchemy 2.0 (async) · PostgreSQL 16 · Alembic · ARQ · Redis
**Infra** Docker · GitHub Actions · Railway · S3 · Resend (M7) · Stripe (M8)
**AI** Claude — static rule content authored at build time, per-finding enrichment cached

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The short version:

- Small PRs. A 1,000-line PR gets an "LGTM" and a bug; a 200-line PR gets a review.
- Every PR answers three questions: **What changed? How is it tested? What's the security impact?**
  The third is not optional here.
- New endpoint → an evil-tenant test. New scanner rule → a known-bad *and* a known-good test.
- **No merge on red.** Not once. Not before a demo.
