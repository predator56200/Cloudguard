# Contributing to CloudGuard AI

## Before your first commit

Read [`docs/08-security-model.md`](docs/08-security-model.md) in full. Not skim — read.

We hold read access to our customers' production AWS accounts. We are, by design, one of the most
attractive supply-chain targets a startup can be. A bug that would be embarrassing at most companies
is existential here.

Then read [`docs/11-coding-standards.md`](docs/11-coding-standards.md).

## Setup

```bash
cp .env.example .env
make dev
make migrate
pip install pre-commit && pre-commit install     # gitleaks, ruff, black, prettier
```

`pre-commit` is not optional. The `gitleaks` hook is the difference between "I almost committed an
API key" and "we rotated every credential and filed a customer disclosure." A secret pushed to git
must be treated as compromised **forever** — rewriting history does not help, because forks, mirrors,
CI caches and clones already have it.

## Workflow

1. **Branch:** `feat/M3-s3-collector` — reference the roadmap task.
2. **Commit:** [Conventional Commits](https://www.conventionalcommits.org) — `feat:`, `fix:`,
   `chore:`, `sec:`, `docs:`, `test:`.
3. **PR:** small. A 1,000-line PR gets an "LGTM" and a bug. A 200-line PR gets a review.
4. **CI must be green.** No exceptions, not once, not before a demo. The first time you override a
   red build is the day the culture dies, and you do not get it back.

## Every PR description answers three questions

```markdown
## What changed?
## How is it tested?
## What is the security impact?
```

The third one is not optional at a security company. Acceptable answers include "none — this is a
CSS change." Unacceptable answers include leaving it blank.

## Definition of Done

A task is done when **all** of these are true:

- [ ] Code + tests, in the same PR. There is no "I'll add tests later." Later never comes.
- [ ] `make lint`, `make typecheck`, `make test` all pass locally.
- [ ] `import-linter` passes — the architecture contract holds (see below).
- [ ] Docs updated if behaviour changed.
- [ ] **New endpoint?** → an evil-tenant test (Org A's token + Org B's resource id → **404**).
- [ ] **New scanner rule?** → a known-bad fixture **and** a known-good fixture. A rule that has
      never been proven to stay *silent* is a rule that will produce false positives, and in
      security tooling a false positive costs more trust than a missed finding costs a customer.
- [ ] **New tenant table?** → RLS enabled, **`FORCE`d**, with **both** `USING` *and* `WITH CHECK`.

## The rules that CI enforces mechanically

You will hit these. They are not negotiable, and each exists because of a specific failure:

| Rule | Enforced by | Why |
|---|---|---|
| `core` may not import `fastapi` or `arq` | `import-linter` | The moment it does, a service can only run inside a web request — so someone copy-pastes it into the worker, and a security rule now has two implementations that will one day disagree. |
| The api and worker may not import each other | `import-linter` | They share code through `core` or not at all. |
| SQLAlchemy may not be imported outside `core.db` | `import-linter` | A router that imports `select()` has bypassed the `org_id`-as-first-argument convention — layer 2 of our tenant isolation. |
| No `any` in TypeScript | ESLint (error) | One `any` at the fetch boundary and the generated API types become decoration; the frontend silently drifts from the backend. |
| `mypy --strict` | CI | `org_id: UUID` in every signature. An unannotated `org_id` accepts `None`, and `None` in a repository means "no tenant filter". **Types are a tenant-isolation control here**, not ergonomics. |
| No `datetime.now()` in `core` | Ruff (`DTZ`) | Time is injected (`core/clock.py`). A test that calls `datetime.now()` fails at midnight on a Tuesday in six months and nobody will know why. |
| No bare `except Exception` | Ruff (`BLE`) | In a security scanner, a swallowed exception becomes "0 findings, score 100" reported to a customer whose cloud is on fire. |
| No secrets in git | gitleaks (pre-commit **and** CI) | Both, deliberately: pre-commit is bypassable (`--no-verify`), so it is a convenience. CI is the control. |

## Migrations

- Every schema change is a migration. `create_all()` **never** runs — not in dev, not in tests.
- **Autogenerate, then read and edit the result.** Autogenerate cannot see RLS policies, partial
  indexes, or enum additions — and those are exactly the things this product depends on.
- **`downgrade()` must actually work.** CI runs `upgrade → downgrade → upgrade` on every PR. A
  migration you cannot roll back is a deploy you cannot undo at 3am.
- Destructive change? **Expand → migrate → contract**, across several deploys. Never in one.

## Adding a scanner rule (from M3)

The most common contribution. Three files, always:

```
packages/core/cloudguard_core/scanner/rules/s3_bucket_public_acl.py   # the pure function
packages/core/cloudguard_core/content/rules/s3_bucket_public_acl.md   # the static knowledge
packages/core/tests/scanner/rules/test_s3_bucket_public_acl.py        # known-bad + known-good
```

Two things people get wrong:

1. **A rule is a pure function.** No network, no database, no `datetime.now()`. `(Resource, ctx) →
   Observation | None`. That purity is why 30 rules test in milliseconds.
2. **`Rule.id` is permanent public API.** It lands in our database, our API, customers' Jira
   tickets, and their suppression configs. **Never rename one.** Deprecate and add.

## Architecture Decision Records

Any decision that would make a new engineer ask *"why on earth is it done this way?"* gets a
numbered file in `docs/adr/`. Append-only — supersede, never rewrite.

The architecture is **frozen** as of M0. Changing it requires an ADR and a conversation, not a PR.
