# 03 — Scanner Engine Design

> Every abstraction is defined here **before** implementation. If an implementation needs a concept
> that isn't in this document, that's a signal to update this document first — not to invent it in
> a pull request.

## The one-sentence design

**Collectors turn AWS into `Resource` objects; the engine evaluates pure `Rule` functions over those
objects to produce `Observation`s; reconciliation turns `Observation`s into stateful `Finding`s.**

The critical property: **I/O and logic are strictly separated.** Collectors do I/O and no logic.
Rules do logic and no I/O. This is what makes 30 rules testable in milliseconds without touching
the network, and it's the difference between a scanner you can extend and one you're afraid of.

```
 AWS  ──Collector──▶  Resource[]  ──RuleEngine──▶  Observation[]  ──reconcile──▶  Finding[]
      (I/O, boto3)    (immutable)   (pure, no I/O)   (facts)        (stateful, DB)  (identity)
```

---

## Abstraction 1 — `Resource`

A normalised, provider-agnostic snapshot of one cloud object. **Immutable** (frozen dataclass).

```
Resource:
    arn: str                  # canonical global identifier — the join key for everything
    type: ResourceType        # enum: S3_BUCKET, IAM_USER, IAM_ROLE, IAM_POLICY, EC2_INSTANCE, SECURITY_GROUP
    account_id: str           # AWS account (12 digits)
    region: str | None        # None for global services (IAM)
    name: str
    tags: dict[str, str]
    config: dict              # normalised, service-specific attributes (see below)
    raw: dict                 # the untouched boto3 response, for evidence and future rules
    collected_at: datetime
```

**Why `config` *and* `raw`?**
`config` is the stable, normalised shape our rules read — e.g. every S3 bucket has
`config["public_access_block"]`, even though boto3 requires four separate API calls to determine
it and throws `NoSuchPublicAccessBlockConfiguration` when it's absent. Normalisation happens **once,
in the collector**, so that 12 rules don't each have to handle that exception. `raw` is kept so that
(a) findings can show real evidence, and (b) a new rule written next month can read a field we
didn't think to normalise today, **without re-scanning**.

**Why ARN as the key?** It is globally unique, stable across renames, and it is the join key the
M9 Fix-First engine will use to map a live resource back to its Terraform address. Choosing ARN
now costs nothing; choosing a name now costs us a migration later.

### Normalised `config` per type (the contract rules depend on)

| Type | Keys |
|---|---|
| `S3_BUCKET` | `public_access_block{...4 flags}`, `acl_grants[]`, `policy` (parsed), `policy_is_public`, `encryption`, `versioning`, `logging`, `mfa_delete` |
| `IAM_USER` | `has_console_access`, `mfa_enabled`, `access_keys[{id, age_days, last_used_days, status}]`, `attached_policy_arns[]`, `inline_policies[]`, `groups[]`, `password_last_used_days` |
| `IAM_ROLE` | `trust_policy` (parsed), `trust_is_public`, `trust_external_principals[]`, `attached_policy_arns[]`, `last_used_days` |
| `IAM_POLICY` | `document` (parsed, default version), `is_customer_managed`, `attachment_count`, `grants_admin`, `wildcard_actions[]`, `wildcard_resources[]` |
| `EC2_INSTANCE` | `public_ip`, `imdsv2_required`, `iam_instance_profile`, `security_group_ids[]`, `ebs_volumes[{encrypted}]`, `state`, `subnet_is_public` |
| `SECURITY_GROUP` | `ingress_rules[{proto, from_port, to_port, cidrs[], sg_refs[]}]`, `egress_rules[...]`, `attached_to[]`, `is_default`, `vpc_id` |

Adding a key to this table is an API change to the rules; it goes through review.

## Abstraction 2 — `Collector`

```
class Collector(Protocol):
    resource_type: ResourceType
    required_permissions: list[str]      # e.g. ["s3:ListAllMyBuckets", "s3:GetBucketAcl"]
    is_global: bool                      # IAM = True (scan once), S3/EC2 = False (per region)

    async def collect(self, ctx: AwsContext) -> AsyncIterator[Resource]: ...
```

- `AwsContext` holds the assumed-role boto3 session, the account id, the region, and the deadline.
- Collectors **stream** (`AsyncIterator`) — an account with 40,000 IAM entities must not be
  materialised in memory.
- Collectors **must never raise on a single-resource failure.** A bucket in a region we can't reach,
  or an `AccessDenied` on one API, degrades that one `Resource` (records a `partial: true` marker
  in `config`) and the scan continues. **A scan that fails entirely because one bucket was weird is
  a scan that never completes for a real customer.** Partial failures are recorded on
  `scans.warnings` and surfaced honestly in the UI ("2 of 47 buckets could not be fully read").
- `required_permissions` is machine-readable and used to (a) generate the CloudFormation policy,
  and (b) pre-flight the connection: on `POST /cloud-accounts/{id}/verify` we simulate/attempt each
  permission and tell the customer *exactly* what's missing, instead of failing silently mid-scan.

**Rate limiting:** every AWS call goes through a shared adaptive retry policy
(`botocore` `retries={"mode": "adaptive", "max_attempts": 5}`) plus a per-service semaphore. IAM's
`GetAccountAuthorizationDetails` is the single most important optimisation available to us: it
returns *all* users, roles, policies, and their attachments in one paginated call. **Use it.** The
naive implementation (list users → for each, list keys, list policies, list groups) is O(n) API
calls and will get a 200-user account throttled into oblivion.

## Abstraction 3 — `Rule`

```
class Rule(Protocol):
    id: str                       # "s3_bucket_public_acl" — stable forever. NEVER renamed.
    applies_to: ResourceType
    severity: Severity            # base severity: CRITICAL | HIGH | MEDIUM | LOW | INFO
    title: str
    cis_refs: list[str]           # e.g. ["CIS-AWS-1.5.0:2.1.5"]

    def evaluate(self, r: Resource, ctx: RuleContext) -> Observation | None: ...
```

**A rule is a pure function.** No network. No database. No clock (`ctx.now` is injected). No
randomness. Given the same `Resource`, it returns the same `Observation` forever. This makes every
rule a 10-line unit test with a known-bad and a known-good fixture, and it makes the whole 30-rule
suite run in under a second.

`RuleContext` carries cross-resource knowledge a single resource can't know:
```
RuleContext:
    now: datetime
    account_id: str
    all_resources: ResourceIndex     # by arn, by type — for rules that need relationships
    account_settings: dict           # e.g. account-level S3 public access block, password policy
```
`ResourceIndex` is what lets a rule like *"EC2 instance is publicly exposed on port 22"* work: the
`SECURITY_GROUP` rule alone can't tell if the SG is *attached* to anything; the EC2 rule needs to
look up its SGs. Cross-resource rules are where the real signal is — and where Prowler is weakest.

**`Rule.id` is a permanent public identifier.** It appears in the DB, the API, customers' Jira
tickets, and their suppression rules. Renaming one is a breaking change. Choose carefully; deprecate,
never rename.

### The rule registry

`@register` decorator populates a module-level registry. `RuleEngine` iterates
`registry.for_type(resource.type)`. Adding a rule = adding one file + one markdown content file +
one test. **No wiring, no config, no if-chain.** A new engineer can ship a rule on day two, and
that is a deliberate design goal — the rule catalogue is the thing that grows forever.

## Abstraction 4 — `Observation`

What a rule returns: **a fact about a resource at a point in time.** Stateless. Not stored.

```
Observation:
    rule_id: str
    resource_arn: str
    severity: Severity            # base, from the rule
    evidence: dict                # the specific values that triggered it — shown in the UI
    context_hints: dict           # inputs to effective-severity (e.g. {"is_prod": true})
```

`evidence` is non-negotiable and it is what separates us from a toy: not *"this SG is open"* but
`{"rule": {"proto":"tcp","port":22,"cidr":"0.0.0.0/0"}, "attached_instances": ["i-0abc"]}`. A
security tool that asserts without showing its work does not get trusted, and does not get renewed.

## Abstraction 5 — `Fingerprint` (finding identity)

```
fingerprint = sha256(f"{cloud_account_id}|{rule_id}|{resource_arn}")
```

This is **the** central design decision of the data model. It answers: *"is this the same problem I
saw yesterday, or a new one?"*

- Deterministic → the same misconfiguration always maps to the same finding row.
- Excludes severity/evidence → a bucket that goes from 1 public grant to 2 is **the same finding**,
  updated, not a new one. Trend charts stay honest.
- Includes `cloud_account_id` → the same rule on the same-named bucket in staging vs prod are
  correctly distinct findings.

**Consequence:** if a customer deletes a resource and recreates it with the same ARN, we resurrect
the old finding (reopen) rather than creating a new one — with `first_seen_at` from the original.
That is the correct security posture: *"you had this problem, you 'fixed' it by deleting, it's back."*

## Abstraction 6 — Reconciliation (the lifecycle state machine)

Pure function. `core/domain/lifecycle.py`. **Zero I/O — this is the most important thing to test.**

```
reconcile(existing: list[Finding], observed: list[Observation], now) -> ReconcileResult
```

| Existing | Observed | Action |
|---|---|---|
| — | yes | **CREATE** `status=open`, `first_seen_at=now`, `last_seen_at=now` → emit `opened` event → enqueue enrichment |
| `open` | yes | **TOUCH** `last_seen_at=now`; if evidence changed, update it → emit `updated` event (only if evidence actually changed — no event spam) |
| `open` | no | **AUTO-RESOLVE** `status=resolved`, `resolved_at=now` → emit `resolved` event |
| `resolved` | yes | **REOPEN** `status=open`, `resolved_at=NULL` → emit `regressed` event ⚠️ *this is a high-value alert: they fixed it and it came back* |
| `suppressed` | yes | **NOOP** (respect the suppression; still update `last_seen_at`) |
| `suppressed` | no | **NOOP** (do not auto-resolve a suppression — expiry handles it) |
| `resolved` | no | **NOOP** |

**Crucial correctness constraint:** auto-resolve may only run on a **complete, successful** scan.
If a scan hit `AccessDenied` on S3, "no observations for S3" does not mean "no S3 problems" — it
means we're blind. So reconciliation is **scoped to the resource types that were successfully
collected**, and a partially-failed scan resolves nothing outside that scope. Getting this wrong
silently marks every finding resolved and reports a perfect security score to a customer whose
credentials just broke. **That single bug would end the company.** It gets a dedicated test.

## Abstraction 7 — Effective severity

```
effective_severity = adjust(rule.severity, resource, context_hints)
```

Base severity is a property of the *rule* ("public S3 bucket = HIGH"). Effective severity is a
property of *this resource in this account*, and it's where we beat a generic scanner:

Escalate when: tags indicate prod (`env=prod|production`) · the resource is *reachable* (SG is
attached to a running instance with a public IP — an open port on an unattached SG is not an
emergency) · the IAM principal has admin · the bucket name matches PII/finance heuristics
(`customer`, `invoice`, `pii`, `backup`, `dump`).
De-escalate when: tags say `env=dev|sandbox|test` · resource is stopped/unattached · a documented
suppression exists.

Both values are stored. **The UI ranks by `effective_severity`; compliance exports show
`severity`.** Never mutate the base severity — a customer must always be able to see the raw,
defensible, standards-aligned rating.

## Abstraction 8 — Rule content (the $0 LLM layer)

Each rule has a companion `content/rules/<rule_id>.md`:

```markdown
---
id: s3_bucket_public_acl
severity: HIGH
service: s3
cis: ["CIS-AWS-1.5.0:2.1.5"]
---
## What this means            <- technical explanation
## Business impact            <- the CEO-readable version
## How to fix                 <- ordered steps
## AWS CLI                    <- ```bash ... ``` (templated: {{bucket_name}})
## Terraform                  <- ```hcl  ... ```
```

Authored once. Reviewed by a human. Seeded into the `rules` table via a data migration.
**Runtime LLM cost: $0.** The LLM's *only* runtime job is `findings.ai_context_md` — the 2–3
sentences that are specific to *this* resource ("bucket `acme-invoices-prod` is tagged `env=prod`
and its name suggests financial records; a public ACL here is likely a reportable data exposure").
Generated **once per finding**, cached forever, regenerated only if `resource.config` changes.

**Security note that engineers get wrong:** bucket names, IAM policy names, and especially **tags**
are attacker-controllable strings that we are about to put in an LLM prompt. Treat them as hostile.
See [08-security-model.md](08-security-model.md) §Prompt injection. The mitigation is architectural,
not a magic prompt: **model output is never allowed to influence control flow** — it can only
produce prose that we render as escaped markdown. It cannot set a severity, resolve a finding, or
choose a remediation.

## The MVP rule catalogue (30 rules)

**IAM (10):** root account has active access keys · root MFA disabled · user without MFA ·
access key older than 90 days · unused access key (>90d) · user with inline admin policy ·
customer-managed policy granting `*:*` · role trusting `*` / any external account without ExternalId ·
unused IAM role (>90d) · password policy weak/absent.

**S3 (7):** public ACL · public bucket policy · public access block not fully enabled ·
no default encryption · no versioning · no access logging · policy allows cross-account write.

**EC2 (6):** instance with public IP in a public subnet · IMDSv2 not enforced (**SSRF → credential
theft; this is how Capital One happened**) · unencrypted EBS volume · instance profile with admin ·
stopped instance >90d (cost + attack surface) · AMI publicly shared.

**Security Groups (7):** SSH (22) open to `0.0.0.0/0` · RDP (3389) open to `0.0.0.0/0` ·
database ports (3306/5432/27017/6379) open to world · all ports (`-1`) open to world ·
default SG has rules · SG open to world **and attached to a running public instance**
(cross-resource, effective-severity CRITICAL) · unrestricted egress on a sensitive workload.

Every rule ships with: implementation + markdown content + a known-bad and a known-good `moto` test.
**A rule without a test does not merge.**
