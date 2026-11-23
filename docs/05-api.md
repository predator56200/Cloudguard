# 05 — API Architecture

Base: `https://api.cloudguard.ai/v1` · JSON only · UTF-8 · `application/problem+json` on errors.

## Conventions

- **Versioned prefix `/v1`.** Cheap now, priceless later.
- **Cursor pagination, never offset.** Offset pagination on a live-updating findings table shows
  duplicates and skips rows as data shifts under the reader. Cursor = opaque base64 of the sort key
  (`last_seen_at`, `id`), HMAC-signed so a client can't forge one to escape their tenant.
- **`Idempotency-Key` required on all POSTs** that create side effects. Stored in Redis for 24h
  keyed `(org_id, endpoint, key)` → replays return the original response. Without this, a customer's
  double-click enqueues two scans.
- **404, never 403, for cross-tenant access.** A `403` confirms the resource exists. That is an
  enumeration oracle.
- **ORM models never touch the wire.** Every response is an explicit Pydantic `*Read` schema. This
  is how `external_id_encrypted` stays out of a JSON payload forever.
- Route templates in metrics/logs, never raw paths (cardinality).

## Authentication

| Method | Header | Used by | Notes |
|---|---|---|---|
| Clerk JWT | `Authorization: Bearer <jwt>` | the dashboard | Verified against cached JWKS. Claims: `sub`, `org_id`, `org_role`, `exp`, `azp`. |
| API key | `Authorization: Bearer cg_live_…` | machine clients (post-MVP) | Argon2id hash compare; `prefix` column narrows the lookup to one row. |
| Webhook signature | `Stripe-Signature` / `svix-*` | Stripe, Clerk | **Verified before the body is parsed.** An unverified webhook is an unauthenticated write endpoint. |
| None | — | `/healthz`, `/v1/public/scan/*` | Rate-limited hard, by IP. |

Every authenticated request resolves to a `Principal(user_id, org_id, role, auth_method)`.
**There is no request without an `org_id`.** No admin backdoor, no "internal" bypass. Support access
is a separate, audited, time-boxed impersonation flow (M8+) that writes to `audit_logs`.

## Authorization

Two roles for the MVP — resist the urge to build RBAC before a customer asks.

| | `member` | `admin` |
|---|---|---|
| Read findings, scores, scans | ✅ | ✅ |
| Trigger a scan | ✅ | ✅ |
| Suppress / mark false-positive | ✅ | ✅ |
| Connect/disconnect a cloud account | ❌ | ✅ |
| Billing, API keys, members, settings | ❌ | ✅ |

Enforced by a FastAPI dependency `require_role("admin")`, not by an `if` inside a handler. It
appears in the OpenAPI schema, so the frontend can hide what the user cannot do — while the backend
still enforces it, because **hiding a button is not authorization.**

---

## Endpoints

### Health
```
GET  /healthz                       200 {"status":"ok"}                       (no deps)
GET  /readyz                        200 {"db":"ok","redis":"ok"} | 503
```

### Cloud accounts
```
POST   /v1/cloud-accounts                      admin
  req  {aws_account_id, alias, regions?[]}
  res  201 {id, status:"pending", external_id, role_name,
            cloudformation_url, template_url, instructions_md}
       ↑ external_id returned EXACTLY ONCE, at creation. Never readable again.

GET    /v1/cloud-accounts                      → CursorPage[CloudAccountRead]
GET    /v1/cloud-accounts/{id}                 → CloudAccountRead   (never includes external_id)
POST   /v1/cloud-accounts/{id}/verify   admin  → attempts AssumeRole + permission pre-flight
  res  200 {status:"active", permissions_ok:true, missing_permissions:[]}
       422 {status:"error", missing_permissions:["s3:GetBucketAcl"], detail}
PATCH  /v1/cloud-accounts/{id}          admin  {alias?, scan_frequency?, regions?}
DELETE /v1/cloud-accounts/{id}          admin  → 204. Cascades. Audit-logged. Requires re-auth.
```

`CloudAccountRead`: `{id, aws_account_id, alias, status, status_detail, scan_frequency, regions,
last_scan_at, last_successful_scan_at, external_id_last4, created_at}`

### Scans
```
POST /v1/scans                 {cloud_account_id}   Idempotency-Key required
  res  202 {scan_id, status:"queued"}   Location: /v1/scans/{id}
       402 if plan limit exceeded · 409 if a scan is already running for that account
GET  /v1/scans/{id}            → ScanRead (polled by the UI every 3s while queued|running)
GET  /v1/scans?cloud_account_id=&status=  → CursorPage[ScanRead]
```
`ScanRead`: `{id, cloud_account_id, status, trigger, started_at, finished_at, duration_ms,
resources_scanned, findings_opened, findings_resolved, warnings[], error_message}`

### Findings — the core surface
```
GET /v1/findings
  ?status=open|resolved|suppressed|false_positive   (repeatable)
  &severity=critical|high|medium|low|info           (repeatable; filters effective_severity)
  &service=iam|s3|ec2|security_group
  &cloud_account_id=&rule_id=&resource_arn=&q=<free text on resource name/arn>
  &sort=severity|first_seen|last_seen   &cursor=&limit=(≤100, default 25)
  res 200 CursorPage[FindingRead] + {"facets": {"severity": {...}, "service": {...}}}
      ↑ facets computed in the same query (FILTER aggregates) so the UI's filter counts
        cost zero extra round-trips.

GET   /v1/findings/{id}          → FindingDetail
PATCH /v1/findings/{id}          {status: "suppressed"|"false_positive"|"open",
                                  reason: str (required to suppress),
                                  expires_at?: date}
  → writes a finding_event + an audit_log. 422 if suppressing without a reason.

GET  /v1/findings/{id}/events    → the timeline
POST /v1/findings/{id}/ask       {question}  → 202, streams back via GET (post-MVP chat)
```

`FindingRead` (list): `{id, rule_id, rule_title, service, severity, effective_severity, status,
resource: {arn, name, type, region}, first_seen_at, last_seen_at, age_days}`

`FindingDetail` (detail) adds: `{evidence, description_md, business_impact_md, remediation_md,
cli_command (rendered, with this resource's values substituted), terraform_snippet (rendered),
ai_context_md, cis_refs, nist_refs, events[], suppression?}`

Note **`cli_command` is rendered server-side** from `rules.cli_template` + the resource — the
frontend must never be responsible for string-substituting a command that a customer will paste
into a production terminal.

### Score
```
GET /v1/score?cloud_account_id=            → {score, delta_7d, delta_30d, counts{...}, computed_at}
GET /v1/score/history?days=90&cloud_account_id=
                                           → [{date, score, counts}]   (from score_snapshots)
```

### Rules
```
GET /v1/rules                → the catalogue (public, cacheable, also our SEO content)
GET /v1/rules/{rule_id}
```

### Suppressions, billing, reports
```
GET/POST/DELETE /v1/suppressions                  admin
GET  /v1/billing/subscription                     admin
POST /v1/billing/checkout-session   {plan}        admin → {url}
POST /v1/billing/portal-session                   admin → {url}
GET  /v1/reports                                  → past weekly reports (S3 presigned, 15-min TTL)
GET  /v1/audit-logs                               admin → CursorPage
```

### Public — the free-scan acquisition loop
```
POST /v1/public/scan          {email, aws_account_id}   heavy IP+email rate limit, captcha
  res 201 {token, external_id, cloudformation_url}
POST /v1/public/scan/{token}/verify   → assume role, run a scan, email the result
GET  /v1/public/scan/{token}          → a public, unindexed, expiring result page (score + top 5)
```
This flow creates a real (unclaimed) `organization` behind the scenes, so claiming it later is a
Clerk sign-up, not a data migration. Results expire in 7 days; connections are revoked after.

### Webhooks
```
POST /v1/webhooks/stripe   → subscription lifecycle → organizations.plan / subscription_status
POST /v1/webhooks/clerk    → organization.created/updated/deleted, user.*, membership.*
```
Both: **verify signature first**, then de-duplicate on the provider's event id (they retry;
replaying `subscription.deleted` after a re-subscribe would downgrade a paying customer), then
process idempotently. Always return `2xx` fast — do the work in a job.

---

## Error handling — RFC 7807

One handler. One shape. Every error.

```json
{
  "type": "https://cloudguard.ai/errors/plan-limit-exceeded",
  "title": "Plan limit exceeded",
  "status": 402,
  "detail": "Your Starter plan allows 1 connected AWS account. You have 1.",
  "instance": "/v1/cloud-accounts",
  "request_id": "018f...",
  "errors": [{"field": "aws_account_id", "message": "…"}]
}
```

| Exception (`core.errors`) | HTTP | When |
|---|---|---|
| `ValidationError` (Pydantic) | 422 | bad input |
| `AuthenticationError` | 401 | missing/invalid token |
| `AuthorizationError` | 403 | authenticated, wrong role (**never for cross-tenant — that's 404**) |
| `NotFoundError` | 404 | absent **or belongs to another tenant** |
| `ConflictError` | 409 | scan already running; duplicate account |
| `PlanLimitError` | 402 | entitlement exceeded |
| `RateLimitError` | 429 | + `Retry-After` |
| `IntegrationError` | 502 | AWS/Claude/Stripe misbehaved |
| `DomainError` (base) | 500 | anything unmapped |

**Never leak internals.** A 500's `detail` is always `"An unexpected error occurred."` plus a
`request_id`; the stack trace goes to Sentry, correlated by that id. A stack trace in an HTTP
response is a free architecture diagram for an attacker — and we are a *security* company.
