# ADR-0001 — Shared-schema multi-tenancy with PostgreSQL Row-Level Security

- **Status:** Accepted
- **Date:** 2026-07-14
- **Deciders:** CTO
- **Supersedes:** —

## Context

CloudGuard is multi-tenant B2B SaaS. Every row of security data belongs to exactly one
organisation, and the architecture must support **10,000 organisations without a rewrite**.

A cross-tenant data leak — one customer seeing another customer's vulnerabilities — is not an
incident for a security vendor. It is an extinction event. No amount of good engineering afterwards
recovers the trust. So the isolation model is the single highest-stakes decision in the system.

Three options were considered.

## Options

### A. Database-per-tenant
Strongest possible isolation: a bug literally cannot cross a database boundary.
**Rejected.** 10,000 databases means 10,000 connection pools (Postgres has a hard
`max_connections`), 10,000 migrations to run and monitor per release, and an operational burden no
small team can carry. It also makes any cross-tenant query — "which rule fires most often across our
customer base?", the input to our own product roadmap — practically impossible.

### B. Schema-per-tenant
Middle ground. **Rejected.** Migrations become a 10,000-iteration loop that can partially fail,
leaving tenants on different schema versions. Postgres's system catalogues degrade with tens of
thousands of schemas. And it does not actually remove the class of bug we are afraid of — the
application still has to select the right schema, and *that* is the same kind of mistake as
forgetting a `WHERE` clause.

### C. Shared schema, `org_id` on every row ✅ **CHOSEN**
One database, one schema, an `org_id NOT NULL` column on every tenant table, and PostgreSQL
Row-Level Security enforcing it.

## Decision

Option C — **but with four independent layers of enforcement**, because a single layer would be
negligent given the stakes:

1. **Identity.** Every request resolves to a `Principal` with a non-null `org_id`. There is no
   unscoped caller: no admin token, no internal bypass, no service account with global read. The
   worker uses the *same* tenant-scoped session path as the API.

2. **Application.** `org_id` is the **first positional parameter of every repository method**. Not a
   filter you remember to add — a parameter you cannot omit without a `TypeError`. `import-linter`
   forbids SQLAlchemy imports outside `core.db`, so no other layer can construct a query at all.

3. **Database.** Row-Level Security:
   ```sql
   ALTER TABLE findings ENABLE ROW LEVEL SECURITY;
   ALTER TABLE findings FORCE  ROW LEVEL SECURITY;
   CREATE POLICY tenant_isolation ON findings
     USING      (org_id = current_setting('app.current_org', true)::uuid)
     WITH CHECK (org_id = current_setting('app.current_org', true)::uuid);
   ```
   with `SET LOCAL app.current_org = '<uuid>'` on every transaction.
   After that, `SELECT * FROM findings` — with no `WHERE` clause — returns only the current tenant's
   rows. **The database physically cannot hand back another customer's data**, even given a buggy
   query, even given a SQL injection.

4. **Tests.** The evil-tenant suite, generated from the OpenAPI schema: for every endpoint, Org A's
   token against Org B's resource id must return **404** (never 403 — a 403 confirms existence and
   is an enumeration oracle). Adding an endpoint without an isolation test is a **CI failure**. You
   cannot forget.

## The three ways this goes wrong (all guarded)

1. **`SET` instead of `SET LOCAL`.** `SET` persists for the whole *connection*, and connections are
   *pooled*. Request A sets org=A, returns the connection, request B inherits org=A. **A
   cross-tenant data breach caused by six missing characters.** `SET LOCAL` is transaction-scoped.

2. **Forgetting `FORCE`.** The table *owner* bypasses RLS by default, and our app role owns the
   tables. Plain `ENABLE ROW LEVEL SECURITY` therefore does *nothing* for us — all the ceremony of
   RLS, none of the protection, and every test still passes.

3. **Forgetting `WITH CHECK`.** `USING` governs reads. Without `WITH CHECK`, a tenant can `INSERT`
   a row carrying someone else's `org_id`. Read-isolated, write-porous.

All three are covered by the M1 RLS migration helper (roadmap task 1.3) and by integration tests
that run against a **real Postgres** — RLS cannot be tested against SQLite, so anyone who mocks the
database here is testing their mock.

## Consequences

**Good**
- One migration, one connection pool, one backup — operable by a small team at 10,000 tenants.
- Cross-tenant analytics (our own product intelligence) remains a normal SQL query.
- RLS **fails closed**: with no `app.current_org` set, the predicate evaluates to NULL and every
  tenant table returns **zero rows**. An accidental unscoped session yields an empty result set, not
  a leak. That is the correct direction to fail.

**Bad / accepted**
- A "noisy neighbour" — one enormous customer — affects shared resources. Mitigated by per-org rate
  limits and queue separation (docs/07).
- RLS adds a small per-query planning cost. Measured in microseconds; irrelevant next to the risk it
  eliminates.
- **[SCALE-LIMIT]** When `findings` exceeds ~500M rows, we hash-partition by `org_id`. That is a
  **migration, not a rewrite** — precisely *because* every row already carries its tenant and every
  query is already org-scoped. The decision made today is what makes tomorrow's fix cheap.
