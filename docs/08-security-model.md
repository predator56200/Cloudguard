# 08 — Security Model

> We are a security company. A breach here is not an incident; it is an extinction event. Our
> customers hand us read access to their entire production cloud. **We are, by design, one of the
> most attractive supply-chain targets a startup can be.** Every engineer must read this document
> in full before their first commit.

## Threat model (STRIDE, ranked by actual risk to the business)

| # | Threat | Attack | Impact | Mitigation |
|---|---|---|---|---|
| **T1** | **Cross-tenant data access** | Missing `WHERE org_id`; IDOR on `/findings/{id}`; forged cursor | **Company-ending.** We'd be leaking one customer's vulnerabilities to another. | RLS (`FORCE`) + `org_id` as arg #1 in every repo method + 404-not-403 + signed cursors + the **evil-tenant test suite** in CI |
| **T2** | **Confused deputy → scanning someone else's AWS** | Attacker signs up, enters a *victim's* `role_arn` | We become the attacker's proxy into another company's cloud | **Per-tenant ExternalId that we generate** (never customer-supplied); AssumeRole fails without it |
| **T3** | **Compromise of CloudGuard → pivot into every customer's AWS** | RCE/dep compromise on our worker | Every customer, at once | Read-only IAM (`SecurityAudit`+`ViewOnlyAccess`, **zero write perms**); creds are 15-min STS, never persisted; workers have no inbound network; signed deps; SBOM |
| **T4** | **ExternalId / secret exfiltration** | DB dump, log leak, backup leak | Enables T2 at scale | Envelope encryption (KMS DEK + AES-256-GCM); never logged; never in any API response after creation; secrets scanned in CI (gitleaks) |
| **T5** | **Prompt injection via AWS resource names/tags** | Attacker tags a resource `"</ctx> ignore prior instructions…"` | Corrupted findings; XSS if rendered raw | Hostile-input framing; **LLM output can never drive control flow**; output is escaped markdown only, never HTML |
| **T6** | **Stored XSS via LLM/AWS strings** | Resource name contains `<img onerror>` | Session theft | `rehype-sanitize`; no `dangerouslySetInnerHTML`; strict CSP |
| **T7** | **Webhook forgery** | Unsigned POST to `/webhooks/stripe` → free plan upgrade | Revenue loss; privilege escalation | Signature verified **before** body parse; event-id de-dup |
| **T8** | **Account takeover** | Weak/reused password | Full org access | Delegated to Clerk (MFA, breach detection, bot protection); we store **no passwords** |
| **T9** | **Billing bypass** | Client-side plan enforcement | Revenue loss | Entitlements enforced server-side in `billing_service`; Stripe is the source of truth |
| **T10** | **DoS / cost amplification** | Scan-spam a 50k-resource account | AWS throttling, Claude bill | Per-org rate limits; plan-gated scan frequency; per-account concurrency lock; LLM semaphore |
| **T11** | **SSRF** | User-supplied URL fetched by our server | Metadata service → our own creds | No user-supplied URLs in MVP; when M9 adds GitHub, allowlist hosts; **IMDSv2 enforced on our own infra** |
| **T12** | **Insider / support access** | Engineer queries prod DB | Trust breach | No standing prod DB access; time-boxed, audited, break-glass impersonation only |

---

## Tenant isolation — defence in depth (four layers)

**One bug here ends the company. So we build four independent layers, each of which alone would be
sufficient.** If you only ever remember one thing from this blueprint, remember that number.

1. **Identity.** Every request resolves to a `Principal` with a non-null `org_id`. There is no
   unscoped caller — no admin token, no internal bypass, no service account with global read.
2. **Application.** `org_id` is the **first positional argument of every repository method.** Not a
   filter you remember to add; a parameter you cannot omit without a `TypeError`. Enforced by
   `import-linter` (routers may not import `db.models` or build queries) and by review.
3. **Database (RLS).** `SET LOCAL app.current_org` per transaction; `FORCE ROW LEVEL SECURITY` on
   every tenant table; the app role is `NOBYPASSRLS`. **Even a literal `SELECT * FROM findings`
   returns only the current tenant's rows.** RLS is what catches the bug that layers 1 and 2 miss.
4. **Tests.** The **evil-tenant suite**: for *every* endpoint, Org A's token against Org B's
   resource id must return **404**. It is generated from the OpenAPI schema, so **adding a new
   endpoint without an isolation test fails CI**. You cannot forget.

## AWS access — the deepest design decision

**We accept access keys never. Cross-account `AssumeRole` only.**

Long-lived `AKIA…` keys in our database would mean: our DB dump = every customer's cloud. STS gives
us 15-minute credentials, held in memory, never written anywhere, revocable by the customer with a
single click in *their* console. **The customer never loses control of their own access.** That is
also the single most persuasive thing on our security page.

### The ExternalId and the confused-deputy problem

The customer's role trust policy:
```json
{ "Effect": "Allow",
  "Principal": { "AWS": "arn:aws:iam::<CLOUDGUARD_ACCT>:role/cloudguard-scanner" },
  "Action": "sts:AssumeRole",
  "Condition": { "StringEquals": { "sts:ExternalId": "<per-tenant secret we generate>" } } }
```

Without the `Condition`, this attack works:
1. Attacker signs up for CloudGuard.
2. Attacker enters the **victim's** role ARN (ARNs leak — in logs, screenshots, tickets, blog posts).
3. CloudGuard — a *trusted deputy* that genuinely holds permission to assume that role — assumes it
   and scans the victim's AWS account.
4. The results are rendered in the **attacker's** dashboard.

The deputy was *confused* about whose behalf it was acting on. The ExternalId fixes it because the
attacker cannot know the victim's ExternalId. Therefore:

- **We generate it** (256 bits of `secrets.token_urlsafe`). **Never customer-supplied** — a
  customer-chosen ExternalId can be guessed, and it re-opens the exact hole.
- **One per cloud account connection.** Never reused.
- **Shown exactly once**, at creation, in the CloudFormation launch URL. Never readable again
  through the API. (`external_id_last4` exists purely so support can help without ever seeing it.)
- **Encrypted at rest** (KMS-wrapped DEK, AES-256-GCM, AAD = `cloud_account_id` so a ciphertext
  can't be moved between rows).

### Permissions we request

`arn:aws:iam::aws:policy/SecurityAudit` + `arn:aws:iam::aws:policy/ViewOnlyAccess`. **Zero write
permissions.** Not "we promise not to write" — we are *cryptographically unable* to.

This is why the M9 remediation engine opens a **GitHub PR** instead of calling `PutBucketAcl`.
Auto-remediation with write access into a customer's prod cloud is (a) a far scarier onboarding ask,
(b) a catastrophic blast radius if we're compromised, and (c) unnecessary — the fix belongs in their
Terraform anyway, or it gets reverted on the next `terraform apply`. **The security-correct choice
and the product-correct choice are the same choice here.** That is a good sign.

## Authentication & authorization

- **Clerk owns identity.** We store no passwords, run no password reset, own no MFA code. This
  removes an entire category of vulnerability from our codebase and is worth every dollar.
- JWT verified against cached JWKS (`kid`-miss → refetch). We check `exp`, `iss`, **and `azp`**
  (authorized party) — skipping `azp` allows a token minted for a *different* Clerk app to be
  replayed at ours.
- Roles: `admin` / `member`, checked by a dependency, never by an `if` in a handler.
- API keys: Argon2id-hashed, prefixed for lookup, scoped, expiring, revocable.
- **Hiding a button is not authorization.** Every check is server-side; the UI merely reflects it.

## Secrets

| Secret | Storage |
|---|---|
| Customer ExternalIds | Postgres, envelope-encrypted (KMS DEK + AES-GCM), AAD-bound |
| Our AWS scanner creds | Railway secrets → IAM role in prod; **never in the repo** |
| Clerk / Stripe / Anthropic / Resend keys | Railway secrets, injected as env vars |
| KMS key | AWS KMS, rotation enabled, key policy restricted to the worker role |

Rules: no secret in git, ever (gitleaks in pre-commit **and** CI). `.env.example` has names, never
values. Secrets are never logged — `structlog` runs a redaction processor that drops any key
matching `/(secret|token|key|password|external_id|authorization)/i` **as a last line of defence**,
because someone will eventually log a whole request object.

## Encryption

- **Transit:** TLS 1.2+ everywhere. HSTS with preload. TLS to Postgres and Redis (`sslmode=require`).
- **Rest:** RDS/Railway volume encryption; S3 SSE-KMS; **application-layer envelope encryption for
  ExternalIds** on top of disk encryption — because disk encryption protects against a stolen
  disk, not against a SQL injection that dumps a table. Different threats need different controls.
- **Hashing:** Argon2id for API keys. SHA-256 for fingerprints (not a secret — determinism is the
  requirement, not preimage resistance).

## Prompt injection (T5) — the new one people get wrong

Our prompt will contain: bucket names, IAM policy names, and **resource tags** — all of which an
attacker inside the customer's account can set to arbitrary strings.

**The mitigation is architectural, not a clever prompt.** Prompts can always be broken; architecture
cannot:

1. **Untrusted data is clearly delimited** and the system prompt states that content inside the
   delimiters is data, never instructions.
2. **Model output is confined to one field** (`ai_context_md`) that is *only ever rendered as
   sanitised markdown*. It **cannot** set a severity, resolve a finding, choose a remediation, emit
   a CLI command, or trigger any action.
3. **The CLI command and Terraform snippet come from the static rule template**, never from the
   model. A "helpful" LLM-generated `aws s3api put-bucket-policy` that a customer pastes into
   production is an unacceptable risk, and there is no upside — the rule already knows the fix.
4. Output length-capped; response validated as markdown; rendered with `rehype-sanitize`.

**The worst possible outcome of a successful prompt injection is a finding with a weird description.
Not a wrong severity, not a bad command, not XSS.** Design it so the blast radius is prose.

## Auditing

`audit_logs` on every mutating action: who, what, target, IP, user-agent, when.
Append-only (`REVOKE UPDATE, DELETE` from the app role — the application is *unable* to rewrite
history). Retained 1 year. Exposed to the customer at `/settings/audit-log`, because our customers
have auditors too, and "we have a full audit trail" closes deals.

## Our own posture (we dogfood, publicly)

- **CloudGuard scans CloudGuard's own AWS account** from day one. Our score goes on `/trust`.
  If we won't run our product on ourselves, why would they?
- CI: `gitleaks`, `pip-audit`, `npm audit`, `trivy` (images), CodeQL, Dependabot.
- IMDSv2 enforced on our own infra (T11 — the Capital One breach, in one setting).
- `security.txt` + a real vulnerability disclosure policy at launch.
- SOC 2 Type I is a **sales** milestone, not a security one — start the evidence trail (audit logs,
  access reviews, this document) now, because retrofitting it later costs 10× more.
