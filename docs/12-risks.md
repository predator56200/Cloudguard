# 12 — Risk Register

Ordered by **expected damage**, not by likelihood. Reviewed at the end of every milestone.
Owner: CTO.

---

## Catastrophic (company-ending)

### R1 — Cross-tenant data leak
*One customer sees another's vulnerabilities.* For a security vendor this is not a bug, it is the
end. No amount of good engineering afterwards recovers the trust.

**Mitigation:** four independent layers ([08](08-security-model.md)): Principal always org-scoped ·
`org_id` as arg #1 in every repo method · Postgres RLS with `FORCE` + `WITH CHECK` · the
schema-generated evil-tenant suite that makes an untested endpoint a CI failure.
**Residual:** low. **Detection:** an alert on any query executing without `app.current_org` set.

### R2 — CloudGuard is compromised and used to pivot into every customer's AWS
We hold the keys to N production clouds. We are a *supply-chain* target by construction.

**Mitigation:** read-only IAM (`SecurityAudit` + `ViewOnlyAccess`) — **we are structurally incapable
of writing to a customer's cloud** · 15-minute STS creds, never persisted · ExternalId envelope-
encrypted with AAD binding · workers have no inbound network · CI supply-chain scanning · dogfooding.
**Residual:** medium — this is inherent to the business. It is why M9 opens a *pull request* instead
of taking write access. **Accept and minimise; never pretend it's solved.**

### R3 — The "silent success" bug: broken scans auto-resolve everything
Credentials break → the collector returns nothing → reconciliation resolves every finding → the
customer sees **score 100, zero findings** and believes they are safe. **We would be actively making
them less secure than having no product at all.** This is, technically, the worst thing our
architecture permits.

**Mitigation:** `scans.collected_types` — reconciliation may only auto-resolve findings for resource
types that were **successfully** collected · partial scans are `status='partial'` with visible
warnings · a dedicated integration test ([10](10-testing.md)) that must never be deleted · the
customer is *emailed* when a connection breaks · a resolved-count spike (>50% in one scan) triggers
an internal alert before it triggers a customer's false confidence.

---

## Severe

### R4 — Nobody buys it
The real risk. The technical plan is sound; the market is crowded and the buyer is unfunded.

**Mitigation:** **5 design partners talking to you by M4, not M8.** The free-scan funnel exists to
generate them. If, at M4, five real companies won't connect an AWS account, **stop and re-evaluate
before building M5–M8.** That is the discipline that separates a startup from a hobby.
*This risk is not mitigated by better code. Do not retreat into the codebase — it's the comfortable
thing to do and it's how technical founders fail.*

### R5 — Alert fatigue: 800 findings, zero fixed
The failure mode of the entire CSPM category. If we ship a longer list, we've built a worse Prowler.

**Mitigation:** 30 high-signal rules, **not 600** · effective-severity ranking (reachability, prod
tags, blast radius) · **M9 is the actual answer** — the product's value metric is *fixes merged*,
not *findings raised*. Design every screen around "what do I do next," never "here is everything."

### R6 — Onboarding friction kills the funnel
Connecting AWS requires a CloudFormation stack in a prod account. Every step loses users.

**Mitigation:** one-click CFN launch URL (pre-filled, no copy-paste) · permission pre-flight that
says *exactly* what's missing instead of failing vaguely · **watch five real people do it and time
them** · the free scan de-risks the first commitment. **Instrument every step of the funnel from
day one** — you cannot fix a drop-off you cannot see.

### R7 — AWS API throttling / a pathological account
A 40,000-IAM-entity account or 10,000 orgs scanning at 02:00:00 sharp → throttling, timeouts,
cascading failures.

**Mitigation:** `GetAccountAuthorizationDetails` (one call, not N+1) · adaptive retry + per-service
semaphores · **jittered scan scheduling** · per-job timeouts · a `scans-large` queue when p99 grows ·
streaming collectors (never materialise the account in memory).

---

## Moderate

### R8 — LLM cost blowout / margin collapse
Naive per-finding-per-scan LLM calls destroy gross margin.

**Mitigation:** static rule content authored once ($0 at runtime) · per-finding enrichment cached on
`ai_context_hash` · a global semaphore · **per-org cost telemetry with alerting from M6.**
Steady-state cost is a function of *new findings/day*, not customers × scans.

### R9 — Prompt injection via AWS tags/names
Attacker-controlled strings enter our LLM prompt.

**Mitigation:** architectural, not prompt-based ([08](08-security-model.md)) — model output can
**only** produce sanitised prose in one field. It cannot set severity, resolve a finding, or emit a
command. **Worst case is a weird description.** Plus a dedicated injection test suite.

### R10 — False positives destroy trust
One wrong "CRITICAL: your database is public" and the customer stops reading. In security tooling,
**precision beats recall** — a missed finding is a gap; a false positive is a lie.

**Mitigation:** every rule has a known-good test proving it stays silent · cross-resource context
(an open SG attached to nothing is not critical) · a one-click "false positive" button that we
*read weekly* · publish the rule logic at `/rules` so customers can audit our reasoning.

### R11 — Terraform mapping (M9) is harder than expected
ARN → HCL address is genuinely hard: modules, `for_each`, dynamic names, no state access.

**Mitigation:** **prototype 9.5 against your own repo in week 1 of M9, before committing to the
rest** · Strategy A (read `tfstate` — exact) with Strategy B (heuristic + confidence score +
"verify this" banner) as the fallback · scope M9 v1 to the ~10 rules with clean, deterministic HCL
fixes (S3 encryption, public access block, SG rules) rather than all 30.

### R12 — Single-founder bus factor / burnout
14 weeks at 20 h/week, alone, while studying.

**Mitigation:** every decision is written down (this directory *is* the mitigation) · CI/CD from
week 1 so no step is manual or memorised · milestones are demoable independently, so stopping is
never catastrophic. **Ship M4 and talk to humans before you exhaust yourself on polish.**

---

## Accepted (documented, not mitigated)

| Risk | Why we accept it |
|---|---|
| Commit-then-enqueue can lose a job on a process crash | The stuck-scan reaper covers it. A transactional outbox is not worth the complexity before revenue. **[SCALE-LIMIT: >100 scans/min]** |
| Railway is a single point of failure | Correct for MVP. Migrating to ECS is a Dockerfile and a Terraform module — the app doesn't change. Do it when a customer asks about our SLA. |
| One Postgres primary | Comfortable to ~10k orgs. Partition `findings` by `org_id` hash when it isn't. **A migration, not a rewrite — because every query is already org-scoped.** |
| No SOC 2 at launch | It's a sales unlock, not a security control. Start the evidence trail now (audit logs, this doc); buy the audit when a deal needs it. |
| AWS only | Deliberate. GCP/Azure before AWS is *deep* is how you build a shallow product that loses to a focused one. |
