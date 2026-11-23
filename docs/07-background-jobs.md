# 07 — Background Jobs

## Why ARQ (and not Celery)

Celery is powerful and it is a swamp: a large config surface, ambiguous async support, a broker
abstraction we don't need (we have Redis and will always have Redis), and failure modes that are
folklore rather than documentation. **ARQ is ~2,000 lines, natively async (matching our async
FastAPI/SQLAlchemy stack with no thread-pool impedance mismatch), and its entire behaviour fits in
your head.** For our workload — a few thousand jobs/day, none of them exotic — ARQ is not a
compromise, it's the correct tool. We chose comprehensibility over capability, deliberately.

**[SCALE-LIMIT]** If we ever need job chaining/DAGs, workflow visualisation, or >1M jobs/day, the
migration path is Temporal (not Celery). Because tasks are thin adapters over `core.services`
([02](02-backend-architecture.md)), that migration touches `apps/worker/tasks/` only — a few
hundred lines. The design already paid for this.

## Queues

Three, because a slow job must never starve a fast one:

| Queue | Jobs | Concurrency | Timeout |
|---|---|---|---|
| `scans` | `run_scan` | 8 | 900s |
| `default` | `enrich_finding`, `verify_cloud_account`, `open_fix_pr` (M9) | 16 | 120s |
| `reports` | `send_weekly_report`, `capture_daily_scores` | 4 | 300s |

Without separation, one enterprise customer's 20,000-resource scan occupies every worker slot and
every other customer's dashboard sits at "queued" for 15 minutes. Queue isolation is cheap
insurance against your best customer degrading everyone else.

**[SCALE-LIMIT]** Add a `scans-large` queue with a dedicated worker pool when p99 scan duration
exceeds ~5 minutes; route by `resources_scanned` from the previous scan.

## The jobs

### `run_scan(org_id, cloud_account_id, scan_id)` — `scans`
`job_id = f"scan:{scan_id}"` — **deterministic.** ARQ deduplicates by job id, so a double-click, a
retried enqueue, and the stuck-scan reaper all converge on exactly one execution. Idempotency by
construction, not by a lock.

Steps: assume role → collect → upsert resources → evaluate rules → reconcile → snapshot score →
fan out enrichment. Detailed in [02](02-backend-architecture.md) and [03](03-scanner-engine.md).

**Concurrency guard:** a Redis lock `lock:scan:{cloud_account_id}` (TTL = job timeout) prevents two
concurrent scans of the same account, which would race on the `resources` upsert and on
reconciliation. Second scan → `409 Conflict` at the API layer.

### `enrich_finding(finding_id)` — `default`
Calls Claude once for the resource-specific context. **Best-effort by design:** if it fails after
retries, the finding is still fully usable — it has the static explanation, remediation, CLI, and
Terraform from the rule catalogue. The AI is a *garnish*, not the meal. A product whose findings are
unreadable during an Anthropic outage is a product with an unacceptable dependency.

Skips if `ai_context_hash == hash(resource.config)` — nothing changed, don't pay again.
Global concurrency capped by a Redis semaphore (protects our rate limit *and* our bill).

### `capture_daily_scores()` — cron `0 1 * * *` — `reports`
Upserts a `score_snapshots` row per active cloud account. Idempotent via
`UNIQUE(cloud_account_id, captured_on)` — running it twice is harmless, which is exactly what you
want from a cron job that might get retried.

### `schedule_daily_scans()` — cron `0 2 * * *` — `default`
Fans out `run_scan` for every `active` account with `scan_frequency='daily'`.
**Jitter: each scan is enqueued with `defer_by = random(0, 3600)s`.** Without jitter, 10,000
customers all get scanned at 02:00:00, we hammer AWS STS, hit throttling, and self-inflict an
outage. Spreading load over an hour is one line of code and it's the difference between working at
scale and not.

### `send_weekly_report(org_id)` — cron `0 13 * * MON` — `reports`
Render HTML → PDF (WeasyPrint) → upload S3 → send via Resend with a presigned link.
Idempotent on `report_deliveries (org_id, week_of)` — **a customer must never receive the same
weekly report twice**, and cron jobs *do* run twice (redeploys, retries, clock skew).

### `reap_stuck_scans()` — cron `*/5 * * * *` — `default`
- `status='queued'` and `created_at < now() - 5min` → re-enqueue (covers the commit-then-enqueue
  crash window described in [02](02-backend-architecture.md)).
- `status='running'` and `started_at < now() - 20min` → mark `failed` ("scan timed out"), release
  the lock.

**This job is the safety net for the entire async system.** Without it, a worker OOM leaves a scan
spinning forever in the UI, and the customer's trust evaporates. Write it in M4, not "later."

### `expire_suppressions()` — cron `0 3 * * *`
Suppressions past `expires_at` → the finding returns to `open`, and a `finding_event` records it.
Security debt is not allowed to become permanent by neglect.

## Retries

ARQ: `max_tries`, exponential backoff with jitter. **Retry policy is per failure class, not global** —
this is where most teams are lazy and pay for it:

| Failure | Retry? | Policy |
|---|---|---|
| AWS throttling (`Throttling`, `RequestLimitExceeded`) | ✅ | 5 tries, exp backoff + jitter |
| AWS transient (5xx, timeout) | ✅ | 3 tries |
| **`AccessDenied` / `AssumeRole` failure** | ❌ | **Do not retry.** Retrying a permission error is pure waste and can look like an attack to their CloudTrail. Mark the account `error`, set `status_detail`, **email the admin**. This is a *product event*, not a *technical failure* — the customer must fix their role. |
| Claude rate limit (429) | ✅ | 5 tries, respect `retry-after` |
| Claude 5xx | ✅ | 3 tries, then give up silently (best-effort) |
| DB serialization failure | ✅ | 3 tries, immediate |
| **Bug in our code (TypeError, etc.)** | ❌ | Fail fast, Sentry, dead-letter. Retrying a bug 5 times just produces 5 identical Sentry events and 5× the load. |

Encoded as: `RetryableError` vs `PermanentError` in `core.errors`. The task wrapper inspects the
type. **A task never contains a bare `except: pass`** — that is how a scanner silently reports
"everything is fine."

## Failure recovery

- **Dead-letter:** after `max_tries`, the job is written to a `failed_jobs` Redis list + Sentry.
  A weekly review of that list is on the CTO's calendar. An unread dead-letter queue is a bug tracker
  nobody opens.
- **Poison pill:** one customer's pathological AWS account (say, 60k IAM entities) must not crash a
  worker repeatedly. Timeouts are enforced per job; a job that times out twice is marked `failed`
  and flagged for manual investigation, not retried forever.
- **Graceful shutdown:** on SIGTERM, ARQ stops accepting new jobs and finishes in-flight work
  (`--graceful-timeout 60`). Railway sends SIGTERM on deploy; without this, every deploy kills every
  running scan.
- **Worker crash:** in-flight jobs are re-queued by ARQ. Because `run_scan` is idempotent
  (deterministic `job_id`, upserts, and reconciliation that converges to the same state), re-running
  a partially-completed scan is *safe*. **This is the payoff for making reconciliation a pure,
  convergent function** — an entire class of "half-finished scan corrupted the data" bugs simply
  cannot occur.
- **Observability:** every job logs `{job_id, org_id, scan_id, duration_ms, outcome}` in structured
  JSON. Metrics: queue depth, job duration p50/p95/p99, failure rate by task. **Alert on queue depth
  > 100 or a p99 scan > 10 min** — queue depth is the earliest possible signal that something is
  wrong, and it precedes customer complaints by ~20 minutes.
