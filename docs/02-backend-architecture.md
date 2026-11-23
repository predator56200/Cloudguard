# 02 — Backend Architecture

## The layers

```
   HTTP request                          Queue job
        │                                     │
        ▼                                     ▼
┌───────────────┐                    ┌────────────────┐
│  apps/api     │                    │  apps/worker   │      ADAPTERS
│  router       │                    │  task          │      (know FastAPI / ARQ)
└───────┬───────┘                    └────────┬───────┘
        │                                     │
        └──────────────┬──────────────────────┘
                       ▼
             ┌──────────────────┐
             │  core/services   │                            USE CASES
             │  ScanService     │                            (know the product)
             └────────┬─────────┘
                      │
        ┌─────────────┼──────────────┬──────────────┐
        ▼             ▼              ▼              ▼
┌─────────────┐ ┌──────────┐ ┌────────────┐ ┌──────────────┐
│ repositories│ │  domain  │ │  scanner   │ │ integrations │  CAPABILITIES
│ (SQL)       │ │ (pure)   │ │ (AWS reads)│ │ (LLM/S3/…)   │
└──────┬──────┘ └──────────┘ └─────┬──────┘ └──────┬───────┘
       ▼                            ▼               ▼
   PostgreSQL                 Customer AWS      Claude/S3/Resend/Stripe
```

**The dependency rule: arrows point down, never up.** `domain` imports nothing of ours.
`services` may import `domain`, `repositories`, `scanner`, `integrations`. Adapters may import
`services`. **Nothing in `core` may import `fastapi` or `arq`.** A CI check enforces this with
`import-linter` — it is not a guideline, it is a build failure.

Why you should care: it means every use case is testable without spinning up an HTTP server, and
the day we need a CLI or an MCP server for CloudGuard, we write an adapter, not a product.

---

## Request lifecycle — `GET /v1/findings?status=open&severity=critical`

1. **Ingress (Railway) → Uvicorn.** TLS terminates at the edge.
2. **`RequestIdMiddleware`** — read `X-Request-ID` or mint a UUIDv7; bind to `structlog` contextvars.
   Every log line for this request, in api *and* in any job it enqueues, carries it. This is how you
   debug production at 2am.
3. **`RateLimitMiddleware`** — Redis token bucket keyed on `org_id` (fallback: IP for unauthed).
   Exceeded → `429` + `Retry-After`.
4. **Authentication** (`deps.get_principal`) — `Authorization: Bearer <clerk_jwt>`.
   Verify signature against Clerk's JWKS (cached in Redis, 1h TTL, refetch on `kid` miss).
   Verify `exp`, `iss`, `azp`. Extract `sub` (user), `org_id`, `org_role`.
   Produces a `Principal(user_id, org_id, role, auth_method)`.
   **A request without a resolvable `org_id` cannot proceed.** There is no "global" caller.
5. **Authorization** (`deps.require_role("admin")` where applicable) — see [08](08-security-model.md).
6. **Tenant-scoped session** (`deps.get_db`) — opens an async SQLAlchemy transaction and immediately
   executes:
   ```sql
   SET LOCAL app.current_org = '<org_id>';
   ```
   Every tenant table has an RLS policy `USING (org_id = current_setting('app.current_org')::uuid)`.
   From this point forward, **the database itself cannot return another tenant's row**, even if a
   developer writes `SELECT * FROM findings` with no WHERE clause. `SET LOCAL` is transaction-scoped,
   so a pooled connection cannot leak the setting to the next request.
7. **Validation** — FastAPI parses query params into a Pydantic `FindingListParams`. Unknown fields
   rejected. Enum values constrained. Cursor decoded and signature-checked.
8. **Router → Service** — `finding_service.list_findings(principal.org_id, params)`.
9. **Service → Repository** — `FindingRepository.list(org_id, filters, cursor, limit)`.
   The repo builds the SQL. **`org_id` is the first positional argument of every repository method**
   — belt (app filter) and braces (RLS).
10. **Serialisation** — ORM objects → `FindingRead` Pydantic schemas → `CursorPage[FindingRead]`.
    ORM models never touch the wire; that's how you accidentally leak `external_id_encrypted`.
11. **Response** — `200` + `X-Request-ID`. Access log emitted with duration, status, org, route
    *template* (never the raw path — raw paths carry IDs and pollute metrics cardinality).

Errors at any step raise a typed exception from `core.errors`; `error_handler.py` is the single
place that maps them to RFC 7807 `application/problem+json`. See [05](05-api.md) §Errors.

## Write lifecycle — `POST /v1/scans` (the "never block" rule)

1. Steps 1–7 as above; body validated; `Idempotency-Key` header required.
2. **Entitlement check** — `billing_service.assert_can_scan(org)`: is the account active, is the
   org within plan limits (scans/day, connected accounts)? Exceeded → `402 Payment Required`.
3. **Insert** `scans` row, `status='queued'`, inside the transaction.
4. **Enqueue** `run_scan(org_id, cloud_account_id, scan_id)` on ARQ — **after commit**, via a
   `after_commit` hook. Enqueueing inside the transaction is a classic bug: the worker picks up the
   job and queries for a `scans` row that hasn't committed yet, and fails.
   *(Accepted trade-off: commit-then-enqueue can lose a job if the process dies in between. Mitigated
   by the `reap_stuck_scans` cron in [07](07-background-jobs.md), which re-enqueues any `queued` scan
   older than 5 minutes. We are choosing a reaper over a full transactional outbox because the outbox
   is not worth the complexity until we have paying customers. This is a **[SCALE-LIMIT]**: at
   >100 scans/min, replace the reaper with an outbox table + relay.)*
5. **Return `202 Accepted`** with `{scan_id, status: "queued"}` and `Location: /v1/scans/{id}`.
   The frontend polls (TanStack Query, 3s interval while `status ∈ {queued, running}`).

**Why not WebSockets/SSE for scan progress?** Because polling a status endpoint every 3 seconds for
90 seconds costs 30 trivially-cached requests and zero new infrastructure, while SSE costs us
sticky connections, a pub/sub fan-out, and a load-balancer configuration we'd have to debug. We add
SSE when a customer asks for it, not before. Boring wins.

## Job lifecycle — `run_scan`

1. ARQ pops the job. `job_id` = `scan:{scan_id}` — **deterministic, so a double-enqueue is a no-op.**
2. Worker opens a tenant-scoped session (same `SET LOCAL app.current_org` mechanism — RLS protects
   the worker exactly as it protects the API; there is no privileged path).
3. `ScanService.execute(scan_id)`:
   - mark `scans.status='running'`, set `started_at`
   - `AwsCredentialBroker.assume(cloud_account)` → short-lived STS credentials (15 min, never stored)
   - **Collect**: each `Collector` lists resources via boto3 (paginated, region-parallel) → `Resource[]`
   - **Persist inventory**: upsert `resources` on `(cloud_account_id, arn)`, refresh `last_seen_at`
   - **Evaluate**: `RuleEngine.evaluate(resources, context)` → `Observation[]` (pure, no I/O)
   - **Reconcile**: `lifecycle.reconcile(existing_findings, observations)` → create / touch /
     auto-resolve. Writes `finding_events` for every state change.
   - **Score**: compute + upsert today's `score_snapshots` row
   - mark `scans.status='success'`, set `finished_at`, counts
4. **Fan out enrichment**: for each newly-created finding, enqueue `enrich_finding(finding_id)`.
   Separate job because Claude is a different failure domain from AWS — a Claude outage must never
   fail a scan, and its retry policy is different.
5. On unhandled exception: mark `scans.status='failed'` with a **sanitised** `error_message`
   (an AWS error can contain ARNs and account IDs — safe for the owning tenant, and only ever shown
   to the owning tenant), then re-raise so ARQ applies its retry policy.

## Configuration & startup

`core/config.py` is a `pydantic-settings` `Settings` object: every environment variable, typed,
with no defaults for secrets. **The process fails to boot if a required variable is missing.**
A service that starts up and *then* fails on first use is a service that pages you at 3am; a
service that refuses to start fails in the deploy pipeline where it belongs.

Health endpoints:
- `GET /healthz` — process is alive. No dependencies checked. Used by Railway's restart policy.
- `GET /readyz` — DB `SELECT 1` + Redis `PING`. Used to gate traffic. Distinguishing these matters:
  a DB blip should stop *traffic*, not trigger a *restart loop*.

## Scaling to 10,000 organisations

| Component | Scaling story |
|---|---|
| API | Stateless. Scale horizontally. Session state lives in Clerk/Redis, never in memory. |
| Worker | Scale horizontally; ARQ competes for jobs. Separate queues so a 10k-resource enterprise scan never starves interactive enrichment (`scans`, `default`, `reports`). |
| Postgres | One primary is comfortable to ~10k orgs. **[SCALE-LIMIT]**: when `findings` passes ~500M rows, partition `findings`/`resources` by `org_id` hash (declarative partitioning — a migration, not a rewrite, precisely because every query is already `org_id`-scoped). Add a read replica for reports first; it's cheaper. |
| Redis | Queue + rate limits + JWKS cache. Single instance is fine; separate the queue from the cache when the cache starts evicting jobs. |
| AWS API limits | Per-*customer* account, so they scale naturally with customers. Global concern is our egress IPs; we allocate a static NAT so customers can allowlist us. |
| Claude | Cached per finding. Steady-state cost is a function of *new* findings/day, not customers × scans. Concurrency-limited with a semaphore; enrichment is best-effort and degrades gracefully. |
