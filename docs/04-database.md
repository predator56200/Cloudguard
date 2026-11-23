# 04 — Database Architecture

## Principles

1. **UUIDv7 primary keys.** Not bigserial (leaks tenant volume, guessable across tenants), not
   UUIDv4 (random → index page splits → write amplification at scale). UUIDv7 is time-sortable, so
   inserts append to the right of the B-tree like a sequence, while remaining unguessable.
2. **`org_id UUID NOT NULL` on every tenant table**, even when derivable via a join. Denormalised on
   purpose: it is what RLS policies filter on and what future partitioning will key on. A join to
   determine tenancy is a join you can forget.
3. **RLS on every tenant table. No exceptions.** Including `audit_logs`.
4. **Timestamps are `TIMESTAMPTZ`, always UTC.** A `TIMESTAMP` column is a future incident.
5. **Money is never floats.** (Only relevant in billing mirrors; use integer cents.)
6. **Enums are Postgres native types**, so bad data cannot exist. Adding a value is a migration.
7. **Soft-delete only where the product needs history** (findings, resources). Everything else is a
   hard delete; a graveyard of `deleted_at` columns is a permanent tax on every query.

---

## Tables

### `organizations`
The tenant. Mirrors a Clerk Organization.

| column | type | notes |
|---|---|---|
| `id` | uuid PK | UUIDv7 |
| `clerk_org_id` | text UNIQUE NOT NULL | sync key from Clerk webhooks |
| `name` | text NOT NULL | |
| `slug` | text UNIQUE NOT NULL | |
| `plan` | enum `plan_t` NOT NULL default `'free'` | free / starter / growth / scale |
| `stripe_customer_id` | text UNIQUE | null until first checkout |
| `stripe_subscription_id` | text | |
| `subscription_status` | enum | active / past_due / canceled / trialing |
| `trial_ends_at` | timestamptz | |
| `created_at`, `updated_at` | timestamptz | |

*No RLS* — this is the tenant root; access is by `id = current_org` only, enforced in the repository.

### `users`
| `id` uuid PK · `clerk_user_id` text UNIQUE · `email` citext · `name` text · `created_at` |

Global, not tenant-scoped: **one human can belong to many orgs** (consultants, agencies — and our
whole M9/MSP story depends on this). A user is *not* owned by an org.

### `memberships`
| `org_id` FK → organizations · `user_id` FK → users · `role` enum(`admin`,`member`) · `created_at` |
PK `(org_id, user_id)`. Mirrors Clerk; Clerk is the source of truth, this is the local read cache
so that authorisation is a DB lookup, not a network call to Clerk on every request.

### `cloud_accounts`
The customer's AWS account connection. **The most security-sensitive table in the system.**

| column | type | notes |
|---|---|---|
| `id` | uuid PK | |
| `org_id` | uuid FK NOT NULL | RLS |
| `provider` | enum `provider_t` default `'aws'` | future-proofing costs one column |
| `aws_account_id` | text NOT NULL | 12 digits, validated |
| `alias` | text | "Production", "Staging" |
| `role_arn` | text NOT NULL | the role *we* assume in *their* account |
| `external_id_encrypted` | bytea NOT NULL | **envelope-encrypted (KMS + AES-GCM). Never plaintext. Never in a log. Never in an API response.** |
| `external_id_last4` | text | for support ("does yours end in …f3a2?") |
| `status` | enum | `pending` / `active` / `error` / `disabled` |
| `status_detail` | text | e.g. "AssumeRole failed: role does not exist" |
| `scan_frequency` | enum | `manual` / `daily` / `hourly` (plan-gated) |
| `regions` | text[] | null = all enabled regions |
| `last_scan_at`, `last_successful_scan_at` | timestamptz | divergence = an alert |
| `created_at`, `updated_at` | | |

UNIQUE `(org_id, aws_account_id)`. **Not** globally unique on `aws_account_id`: an MSP and their
client may both legitimately connect the same account. But — see [08](08-security-model.md) — a
*new* org connecting an `aws_account_id` already connected elsewhere raises a review flag, because
it's also what account-takeover reconnaissance looks like.

### `scans`
| `id` uuid PK · `org_id` FK · `cloud_account_id` FK · `status` enum(`queued`,`running`,`success`,`partial`,`failed`) · `trigger` enum(`manual`,`scheduled`,`onboarding`,`api`) · `started_at` · `finished_at` · `duration_ms` int · `resources_scanned` int · `findings_opened` int · `findings_resolved` int · `collected_types` text[] · `warnings` jsonb · `error_message` text · `created_at` |

`collected_types` is load-bearing: reconciliation may only auto-resolve findings whose resource type
is in this array. See [03](03-scanner-engine.md) §Reconciliation. It is the guard against the
"broken credentials → perfect security score" catastrophe.

### `resources`
Inventory snapshot. Soft-deleted (we keep history).

| `id` uuid PK · `org_id` FK · `cloud_account_id` FK · `arn` text NOT NULL · `type` enum · `region` text · `name` text · `tags` jsonb · `config` jsonb · `raw` jsonb · `first_seen_at` · `last_seen_at` · `deleted_at` (set when a successful scan no longer sees it) |

UNIQUE `(cloud_account_id, arn)` — the upsert target.
`raw` can be large; **[SCALE-LIMIT]**: if `resources` exceeds ~50 GB, move `raw` to S3 and store a
key. Not before — premature, and jsonb + TOAST compresses it well.

### `rules`
The catalogue. **Seeded from `packages/core/content/rules/*.md` by data migration**, not by hand.

| `id` text PK (`s3_bucket_public_acl`) · `title` · `service` enum · `severity` enum · `description_md` · `business_impact_md` · `remediation_md` · `cli_template` · `terraform_template` · `cis_refs` text[] · `nist_refs` text[] · `version` int · `enabled` bool · `updated_at` |

Global, not tenant-scoped. Why in the DB at all if it's authored in code? Because
`findings.rule_id` needs a real FK (integrity), because the API serves the catalogue, and because
a future "custom rules" feature has a home. Code remains the source of truth; the table is a
projection.

### `findings` ⭐ the heart of the product
| column | type | notes |
|---|---|---|
| `id` | uuid PK | |
| `org_id` | uuid FK NOT NULL | RLS |
| `cloud_account_id` | uuid FK NOT NULL | |
| `rule_id` | text FK → rules | |
| `resource_id` | uuid FK → resources | |
| `resource_arn` | text NOT NULL | denormalised: survives resource deletion, needed for M9 |
| `fingerprint` | text NOT NULL | `sha256(cloud_account_id|rule_id|resource_arn)` |
| `status` | enum | `open` / `resolved` / `suppressed` / `false_positive` |
| `severity` | enum | base, from the rule — never mutated |
| `effective_severity` | enum | context-adjusted — what the UI ranks by |
| `evidence` | jsonb NOT NULL | the specific values that triggered it |
| `first_seen_at` | timestamptz | **never updated on reopen** → true MTTR |
| `last_seen_at` | timestamptz | |
| `resolved_at` | timestamptz | |
| `ai_context_md` | text | Claude, cached |
| `ai_context_hash` | text | hash of the `resource.config` it was generated from → regen trigger |
| `ai_generated_at` | timestamptz | |
| `created_at`, `updated_at` | | |

**UNIQUE `(cloud_account_id, fingerprint)`** — the database itself enforces "one finding per problem
per account." A duplicate-finding bug is impossible by construction, not by discipline.

### `finding_events`
Append-only audit trail per finding. **Never updated, never deleted.**

| `id` · `org_id` · `finding_id` FK · `event_type` enum(`opened`,`updated`,`resolved`,`regressed`,`suppressed`,`unsuppressed`,`marked_false_positive`,`commented`) · `actor_type` enum(`system`,`user`) · `actor_user_id` · `metadata` jsonb · `created_at` |

This is what makes "your team fixed 23 issues this month" true rather than marketing. It is also the
audit evidence a customer's own auditor will ask for.

### `suppressions`
| `id` · `org_id` · `rule_id` · `resource_pattern` text (ARN glob) · `reason` text NOT NULL · `expires_at` timestamptz · `created_by` FK users · `created_at` · `revoked_at` |

**`reason` is NOT NULL and `expires_at` defaults to 90 days.** A suppression without a reason is
how security debt becomes permanent and invisible. We force an expiry so it comes back for review —
this is a product opinion, and it is correct.

### `score_snapshots`
| `id` · `org_id` · `cloud_account_id` · `captured_on` DATE · `score` smallint (0–100) · `counts` jsonb `{critical, high, medium, low, info, resources}` · `created_at` |

UNIQUE `(cloud_account_id, captured_on)` — idempotent daily upsert. Pre-aggregated so the trend
chart is one indexed range scan, not an aggregate over millions of findings. This is the difference
between a dashboard that loads in 40ms at 10,000 orgs and one that times out.

**Score algorithm** (`core/domain/scoring.py`, pure, versioned):
```
penalty = 15·critical + 7·high + 3·medium + 1·low     (per-severity weights)
score   = round(100 · exp(-penalty / (25 + 5·log2(1 + resource_count))))
```
Exponential decay, normalised by account size, so a 500-resource company with 4 criticals doesn't
score the same as a 5-resource company with 4 criticals. Bounded 0–100, monotonic, never negative.
**The formula is versioned in the snapshot row** — when we change it, historical charts don't lie.

### `remediations` (M9)
| `id` · `org_id` · `finding_id` FK · `kind` enum(`terraform_pr`,`cli`,`manual`) · `repo_full_name` · `pr_number` · `pr_url` · `pr_state` enum(`open`,`merged`,`closed`) · `iac_file_path` · `iac_resource_address` · `diff` text · `opened_at` · `merged_at` |

### `api_keys`
| `id` · `org_id` · `name` · `key_hash` text (**Argon2id of the key; the key itself is shown once and never stored**) · `prefix` text (`cg_live_a1b2`, for display) · `scopes` text[] · `last_used_at` · `expires_at` · `revoked_at` |

### `audit_logs`
| `id` · `org_id` · `actor_user_id` · `actor_type` · `action` text (`cloud_account.created`) · `target_type` · `target_id` · `ip` inet · `user_agent` · `metadata` jsonb · `created_at` |

Append-only. RLS-protected. **Every mutating API call writes one.** Retained 1 year.

### `notification_settings`, `report_deliveries`
Weekly-report configuration and delivery log (idempotency: never send the same week's report twice).

---

## Relationships

```
organizations ─┬─< memberships >─ users
               ├─< cloud_accounts ─┬─< scans
               │                   ├─< resources ─< findings
               │                   └─< score_snapshots
               ├─< findings ─┬─< finding_events
               │             └─< remediations
               ├─< suppressions
               ├─< api_keys
               └─< audit_logs

rules ─< findings          (global catalogue, not tenant-scoped)
```

**Delete semantics:** `ON DELETE CASCADE` from `organizations` down (a GDPR erasure request must be
one statement). `ON DELETE RESTRICT` from `rules` (never orphan a finding). `resources.deleted_at`
is a soft delete — findings must outlive their resource so we can show "you deleted the exposed
bucket" rather than losing the record.

## Indexes (and why each exists)

| Index | Serves |
|---|---|
| `findings (org_id, status, effective_severity DESC, last_seen_at DESC)` | **The** dashboard query. Composite order matters: equality columns first, then range/sort. |
| `findings (cloud_account_id, fingerprint)` UNIQUE | Reconciliation lookup + duplicate prevention. Every scan hits this. |
| `findings (org_id, rule_id) WHERE status='open'` | "Which rule fires most?" — partial index; 90% of rows are excluded. |
| `findings (resource_id)` | Resource detail page. |
| `resources (cloud_account_id, arn)` UNIQUE | Collector upsert target. |
| `resources (org_id, type) WHERE deleted_at IS NULL` | Inventory views. |
| `resources USING gin (tags)` | Tag filtering ("show me prod"). GIN because jsonb. |
| `scans (cloud_account_id, created_at DESC)` | Scan history. |
| `scans (status) WHERE status IN ('queued','running')` | The stuck-scan reaper. Tiny partial index. |
| `score_snapshots (cloud_account_id, captured_on DESC)` | Trend chart. |
| `finding_events (finding_id, created_at DESC)` | Finding timeline. |
| `audit_logs (org_id, created_at DESC)` | Audit view. |

**Rule:** every index is added *with the query it serves in the commit message*, and we `EXPLAIN
ANALYZE` before merging. Indexes are not free — they tax every write, and the write path (scans) is
our hot path. An index nobody can name a query for gets deleted.

## Row-Level Security

Applied to every tenant table:

```sql
ALTER TABLE findings ENABLE ROW LEVEL SECURITY;
ALTER TABLE findings FORCE ROW LEVEL SECURITY;   -- applies even to the table owner
CREATE POLICY tenant_isolation ON findings
  USING      (org_id = current_setting('app.current_org', true)::uuid)
  WITH CHECK (org_id = current_setting('app.current_org', true)::uuid);
```

- `USING` governs read; `WITH CHECK` governs write — **without `WITH CHECK`, a tenant could INSERT
  a row belonging to another tenant.** People forget this constantly.
- `FORCE` matters because our app role owns the tables, and owners bypass RLS by default. Forgetting
  `FORCE` means RLS silently does nothing. This is the single most common way teams *think* they
  have RLS and don't.
- The app connects as `cloudguard_app` (NOBYPASSRLS). Migrations run as a separate,
  higher-privilege role that the running application does not have credentials for.
- `SET LOCAL app.current_org = …` on every transaction (see [02](02-backend-architecture.md)).
  `LOCAL` = transaction-scoped, so a pooled connection can never leak the setting to the next
  request. Using `SET` instead of `SET LOCAL` here would be a cross-tenant data breach. It is
  guarded by an integration test that runs on every commit.

## Migrations (Alembic)

- **Every schema change is a migration. No exceptions, no `create_all()` in any environment.**
- One migration per PR. Autogenerate, then **read and edit it** — autogenerate misses RLS policies,
  partial indexes, and enum changes.
- **Every migration must be reversible** (`downgrade()` implemented and *tested* in CI by running
  `upgrade → downgrade → upgrade`).
- **Expand → migrate → contract** for anything destructive. To rename a column:
  1. add the new column (deploy), 2. dual-write (deploy), 3. backfill, 4. read from new (deploy),
  5. drop the old (deploy). Five deploys. Zero downtime. This is what "no rewrite at 10,000 orgs"
  actually costs, and it's cheap.
- **Never `ALTER TABLE … ADD COLUMN NOT NULL DEFAULT` on a large table without checking lock
  behaviour**; PG11+ makes constant defaults safe, volatile ones are a full rewrite under an
  ACCESS EXCLUSIVE lock. Set `lock_timeout = '3s'` in every migration so a bad one *fails* instead
  of taking the product down while it waits.
- Data migrations (e.g. seeding the rule catalogue) are separate, idempotent, and re-runnable.
