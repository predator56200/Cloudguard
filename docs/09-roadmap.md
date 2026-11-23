# 09 — Development Roadmap

Every task is scoped to **< 1 working day** for a competent engineer. Tasks are ordered; within a
milestone, `→` marks a hard dependency. Estimates assume ~20 h/week (a CS student with classes).

**Definition of Done for every task:** code + tests + types pass CI + docs updated if behaviour
changed. There is no "I'll add tests later." Later never comes, and this is a security product.

---

## M0 — Foundations (1 week)

| # | Task | Deliverable |
|---|---|---|
| 0.1 | Init monorepo skeleton, `.gitignore`, `.editorconfig`, LICENSE | tree matches [01](01-repository-structure.md) |
| 0.2 | `packages/core` package with `pyproject.toml`; installable in editable mode | `import cloudguard_core` works |
| 0.3 | `core/config.py` — pydantic-settings; all env vars; fails fast; `.env.example` | boot fails loudly on a missing var |
| 0.4 | `core/logging.py` — structlog, JSON in prod, secret-redaction processor | `log.info("x", org_id=…)` emits JSON |
| 0.5 | `core/errors.py` — full exception hierarchy ([11](11-coding-standards.md)) | |
| 0.6 | `core/clock.py`, `core/ids.py` (UUIDv7) | frozen clock usable in tests |
| 0.7 | `apps/api` FastAPI skeleton + app factory + `/healthz` + `/readyz` | `curl localhost:8000/healthz` |
| 0.8 | `apps/worker` ARQ skeleton + a `ping` task | job runs |
| 0.9 | `docker-compose.yml`: postgres 16, redis 7, api, worker | `make dev` works |
| 0.10 | Alembic wired; first empty migration; `make migrate` | `alembic upgrade head` |
| 0.11 | `apps/web` Next.js 15 + TS strict + Tailwind + shadcn init | landing page renders |
| 0.12 | `Makefile` (dev/test/lint/migrate/types/seed) | |
| 0.13 | `.pre-commit-config.yaml`: ruff, black, mypy, eslint, gitleaks | |
| 0.14 | `ci.yml`: lint → typecheck → test → build, on every PR | green badge |
| 0.15 | `import-linter` contract: `core` may not import fastapi/arq | CI fails if violated |
| 0.16 | Deploy the empty skeleton to Railway (api + worker + web + pg + redis) | **a live URL on day 7** |

> **Why deploy an empty app?** Because "it works on my machine" is where startups die. Every
> subsequent milestone deploys continuously. Deploying is now a non-event forever.

---

## M1 — Auth & Tenancy (1 week)

| # | Task |
|---|---|
| 1.1 | Clerk app; enable **Organizations**; configure JWT template with `org_id` + `org_role` |
| 1.2 | Models: `organizations`, `users`, `memberships` + migration |
| 1.3 | **RLS migration helper**: an Alembic op that enables + FORCEs RLS and adds the tenant policy → reuse for every future table |
| 1.4 | Two DB roles: `cloudguard_app` (NOBYPASSRLS) and `cloudguard_migrator` |
| 1.5 | `core/db/session.py` — async engine + `TenantSession` that emits `SET LOCAL app.current_org` |
| 1.6 | `core/db/repositories/base.py` — generic `Repository[T]`, `org_id` as arg #1 |
| 1.7 | `api/security/clerk_jwt.py` — JWKS fetch + Redis cache, verify `exp`/`iss`/`azp` |
| 1.8 | `api/security/principal.py` + `deps.get_principal` / `require_role` |
| 1.9 | `POST /v1/webhooks/clerk` — signature verify + org/user/membership sync (idempotent) |
| 1.10 | `GET /v1/me` — returns principal + org. First authenticated endpoint. |
| 1.11 | Frontend: ClerkProvider, sign-in/sign-up routes, `(dashboard)` auth+org guard |
| 1.12 | Frontend: BFF proxy route handler (`/api/proxy/[...path]`) |
| 1.13 | **Evil-tenant test harness** — the fixture that mints two orgs and asserts 404 across them |
| 1.14 | RLS integration test: raw `SELECT * FROM findings` as `cloudguard_app` returns only own rows |

> **Deliverable:** two real orgs can sign up, and neither can see the other. Prove it with a test,
> not with a vibe.

---

## M2 — AWS Onboarding (1.5 weeks)

| # | Task |
|---|---|
| 2.1 | Provision **our** AWS account: scanner IAM role, KMS key, S3 bucket (Terraform in `infra/`) |
| 2.2 | `core/crypto.py` — envelope encryption (KMS DEK + AES-256-GCM, AAD-bound) + unit tests |
| 2.3 | `cloud_accounts` model + migration + RLS |
| 2.4 | `infra/cloudformation/cloudguard-role.yml` — the role, trust policy w/ ExternalId, managed policies |
| 2.5 | ExternalId generation (256-bit) + one-time reveal semantics |
| 2.6 | `POST /v1/cloud-accounts` → returns CFN launch URL + ExternalId (once) |
| 2.7 | `core/scanner/aws.py` — `AwsCredentialBroker.assume()` (STS, 15-min, in-memory only) |
| 2.8 | Permission pre-flight: attempt each `required_permission`, report exactly what's missing |
| 2.9 | `POST /v1/cloud-accounts/{id}/verify` → `active` or a precise, actionable error |
| 2.10 | `GET/PATCH/DELETE /v1/cloud-accounts` + audit logging |
| 2.11 | Frontend `/onboarding`: `ConnectAwsWizard`, one-click CFN launch button, ExternalId reveal |
| 2.12 | Frontend `ConnectionVerifier` — polls `/verify`, shows the precise failure with a fix |
| 2.13 | Tests: `moto` + a **real** AssumeRole against a sandbox account (manual gate, run once) |

> **This is the highest-drop-off screen in the entire product.** If connecting AWS is confusing,
> nothing downstream matters. Budget the extra half-week here and *watch a real person do it*.

---

## M3 — Scanner Engine (2.5 weeks)

| # | Task |
|---|---|
| 3.1 | `scanner/models.py` — `Resource`, `Observation`, `RuleContext`, `ResourceIndex`, enums |
| 3.2 | `scanner/registry.py` — `@register` decorator + lookup by type |
| 3.3 | `scanner/engine.py` — `RuleEngine.evaluate(resources, ctx)` (pure) |
| 3.4 | `Collector` protocol + `AwsContext` + adaptive-retry/paginator helpers |
| 3.5 | `collectors/s3.py` (+ normalisation of the 4 public-access APIs into one shape) |
| 3.6 | `collectors/iam.py` — **must use `GetAccountAuthorizationDetails`**, not N+1 calls |
| 3.7 | `collectors/ec2.py` (instances, volumes, IMDS options, subnet publicness) |
| 3.8 | `collectors/security_groups.py` |
| 3.9 | Partial-failure handling: per-resource degradation, `scans.warnings`, never abort the scan |
| 3.10 | Rules: S3 ×7 (impl + content md + 2 tests each) |
| 3.11 | Rules: IAM ×10 |
| 3.12 | Rules: EC2 ×6 |
| 3.13 | Rules: Security Groups ×7 (incl. the cross-resource "open **and attached to running public instance**") |
| 3.14 | `domain/severity.py` — effective-severity adjustment + tests |
| 3.15 | `moto` fixture library: a "known-bad account" and a "known-good account" |
| 3.16 | Golden test: scan the bad account → exactly the expected 30 rule ids fire. No more, no less. |

---

## M4 — Findings, Lifecycle & Score (1.5 weeks)

| # | Task |
|---|---|
| 4.1 | `domain/fingerprint.py` + tests |
| 4.2 | Models: `resources`, `rules`, `findings`, `finding_events`, `suppressions`, `score_snapshots` + migrations + RLS |
| 4.3 | Data migration: seed the `rules` table from `content/rules/*.md` (idempotent, re-runnable) |
| 4.4 | `domain/lifecycle.py` — the reconciliation state machine (pure) |
| 4.5 | **Lifecycle test matrix** — all 7 transitions, incl. reopen-after-resolve |
| 4.6 | **The critical test:** a partial scan (S3 `AccessDenied`) must resolve **nothing** in S3 |
| 4.7 | `domain/scoring.py` — the score formula, versioned + tests (0–100, monotonic, size-normalised) |
| 4.8 | `services/scan_service.py` — the full pipeline, end to end |
| 4.9 | `worker/tasks/scan.py` — deterministic `job_id`, Redis per-account lock |
| 4.10 | `POST /v1/scans` (202 + idempotency key) and `GET /v1/scans/{id}` |
| 4.11 | Repos: `findings` (filters, facets, cursor pagination), `resources`, `scores` |
| 4.12 | `GET /v1/findings` (+ facets in one query), `GET /v1/findings/{id}`, `PATCH` (suppress) |
| 4.13 | `GET /v1/score` + `/v1/score/history` |
| 4.14 | `reap_stuck_scans` cron ← **do not defer this** |
| 4.15 | Integration test: onboard → scan a moto account → 30 findings → fix one → rescan → it auto-resolves, score rises |

> **End of M4 = the product works.** Everything after this is making it usable, sellable, and
> beautiful. This is the moment to demo it to your first 5 design partners.

---

## M5 — Dashboard (2.5 weeks)

| # | Task |
|---|---|
| 5.1 | `make types` — OpenAPI → `packages/ts-types`; CI drift check |
| 5.2 | `lib/api-client.ts` (typed fetch) + `lib/query-keys.ts` + `QueryProvider` |
| 5.3 | Dashboard shell: sidebar, org switcher, top bar, mobile nav |
| 5.4 | `ScoreGauge` + `ScoreTrendChart` (Recharts, 90-day) |
| 5.5 | `SeverityBreakdown` + `TopFindings` + `AccountHealth` cards |
| 5.6 | `/findings`: `DataTable`, virtualised, sortable |
| 5.7 | `FindingsFilters` — **URL-backed** (nuqs), with facet counts |
| 5.8 | `SeverityBadge` (colour + icon + label — never colour alone) |
| 5.9 | `/findings/[id]`: explanation, business impact, evidence viewer |
| 5.10 | `RemediationTabs`: Console / **AWS CLI (copy)** / **Terraform (copy)** |
| 5.11 | `SuppressDialog` (reason required, expiry default 90d) + optimistic update |
| 5.12 | `FindingTimeline` from `finding_events` |
| 5.13 | `/cloud-accounts` + detail (scan history, warnings, health) |
| 5.14 | `FirstScanProgress` — live polling during the first scan (**the magic moment**) |
| 5.15 | Loading / empty / error states for every view |
| 5.16 | Playwright E2E: sign up → connect (mocked AWS) → scan → see findings → suppress one |

---

## M6 — AI Enrichment (1.5 weeks)

| # | Task |
|---|---|
| 6.1 | `integrations/llm` — `LLMClient` protocol, `AnthropicClient`, `FakeLLMClient` |
| 6.2 | Author + review all 30 `content/rules/*.md` (**this is a writing task, and it is the product**) |
| 6.3 | Enrichment prompt: hostile-input delimiting, output-shape constraint, length cap |
| 6.4 | `services/enrichment_service.py` — cache on `ai_context_hash`, skip when unchanged |
| 6.5 | `worker/tasks/enrich.py` — Redis semaphore, retry policy, **best-effort degradation** |
| 6.6 | Fan-out from `run_scan` for newly-opened findings only |
| 6.7 | `AiContextCard` + `MarkdownRenderer` with `rehype-sanitize` |
| 6.8 | **Prompt-injection test suite**: tags/bucket names containing injections + XSS payloads must produce inert, escaped prose — never HTML, never a changed severity |
| 6.9 | Cost telemetry: tokens + $ per org per day, logged and alertable |

---

## M7 — Jobs, Reports & Email (1 week)

| # | Task |
|---|---|
| 7.1 | ARQ queues (`scans`/`default`/`reports`) + per-queue concurrency + graceful shutdown |
| 7.2 | `schedule_daily_scans` cron **with jitter** |
| 7.3 | `capture_daily_scores` cron (idempotent upsert) |
| 7.4 | `expire_suppressions` cron |
| 7.5 | Weekly report HTML template (score, delta, new criticals, fixed count, top 5) |
| 7.6 | HTML → PDF (WeasyPrint) → S3 (SSE-KMS) → presigned URL |
| 7.7 | `integrations/email` — `EmailClient` protocol + Resend + fake |
| 7.8 | `send_weekly_report` — idempotent on `(org_id, week_of)` |
| 7.9 | Transactional emails: scan failed, **AWS connection broken** (a product event, not a log line), new critical finding |
| 7.10 | `/settings/notifications` + unsubscribe (one click, no login — CAN-SPAM) |

---

## M8 — Billing & Launch (1.5 weeks)

| # | Task |
|---|---|
| 8.1 | Stripe products/prices: Free / Starter $99 / Growth $299 / Scale $799 |
| 8.2 | `services/billing_service.py` — entitlements: accounts, scan frequency, history retention |
| 8.3 | `POST /v1/billing/checkout-session` + `/portal-session` |
| 8.4 | `POST /v1/webhooks/stripe` — verify → de-dup on event id → update plan |
| 8.5 | Server-side entitlement enforcement (402) at every gated call site |
| 8.6 | `/settings/billing` + upgrade prompts at the limit |
| 8.7 | `/v1/public/scan/*` — the **free instant scan** funnel (heavy rate limit + captcha) |
| 8.8 | Public result page (`noindex`, 7-day expiry, auto-revoke), "claim this scan" → Clerk sign-up |
| 8.9 | Marketing: landing, pricing, `/rules` catalogue (**30 SEO pages, and they're already written**) |
| 8.10 | `/trust` page — **our own CloudGuard score, live** |
| 8.11 | Sentry (api/worker/web), uptime checks, alerting on queue depth + scan p99 |
| 8.12 | Run CloudGuard against CloudGuard. Fix what it finds. Publish the score. |
| 8.13 | `security.txt`, vulnerability disclosure policy, privacy policy, ToS, DPA template |

> **MVP complete: ~14 weeks.**

---

## M9 — ⭐ The Moat: Fix-First Remediation PRs (3–4 weeks)

The reason we exist. Do not start it before M4 is genuinely solid.

| # | Task |
|---|---|
| 9.1 | GitHub App: manifest, permissions (`contents:write`, `pull_requests:write`), install flow |
| 9.2 | `integrations/github` — installation tokens, repo read, branch, commit, PR |
| 9.3 | Repo connection UI + `github_installations` table |
| 9.4 | **IaC discovery**: walk the repo, find `.tf` files, parse with `python-hcl2` |
| 9.5 | **ARN → Terraform address mapping.** Strategy A: read `terraform.tfstate` if the customer grants access to their state backend (exact). Strategy B: heuristic match on resource name/tags (fuzzy, needs a confidence score). **Ship A; fall back to B with a "verify this" banner.** |
| 9.6 | `remediations` table + migration |
| 9.7 | Fix generators per rule (a rule declares its own HCL patch — **deterministic, template-based, not LLM-generated**) |
| 9.8 | PR body: finding, evidence, business impact, the diff, a link back to CloudGuard |
| 9.9 | `open_fix_pr(finding_id)` task + `POST /v1/findings/{id}/remediate` |
| 9.10 | PR status webhook → `remediations.pr_state`; on merge + next scan → finding auto-resolves → **"CloudGuard fixed this"** |
| 9.11 | The metric that sells the company: **fixes merged / month**, on the dashboard and in the weekly email |
| 9.12 | Safety rails: never touch >1 resource per PR; never modify a file outside the mapped module; a dry-run diff preview before the first-ever PR |

> **Task 9.5 is the hardest engineering problem in the company.** It is also the moat. If it were
> easy, Wiz would have shipped it. Prototype it against your *own* Terraform repo in week one of M9
> before committing to the rest.
