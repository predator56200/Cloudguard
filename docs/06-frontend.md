# 06 — Frontend Architecture

Next.js 15 (App Router) · TypeScript strict · Tailwind · shadcn/ui · Clerk · TanStack Query.

## The mental model: two kinds of data

This is the decision that determines whether the App Router helps you or fights you.

| Kind | Rendering | Why |
|---|---|---|
| **Static / SEO / first paint** — marketing, pricing, the public rules catalogue, the shell of the dashboard | **Server Components** | Fast, indexable, no JS shipped. |
| **Live, filtered, user-mutable** — findings table, score, scan status | **Client Components + TanStack Query** | Needs polling, optimistic updates, cache invalidation, filter state in the URL. Server Components cannot do this without a full round-trip per keystroke. |

**Anti-pattern we will not adopt:** fetching findings in a Server Component and re-rendering the
whole route on every filter change. It feels idiomatic and it is miserable — every filter click
becomes a server round-trip with no cache and no optimistic UI. The findings table is an
*application*, not a *document*. Fetch it on the client.

## Routing

```
app/
├── (marketing)/                       ← Server Components, statically generated
│   ├── page.tsx                       /                 landing
│   ├── pricing/page.tsx               /pricing
│   ├── scan/page.tsx                  /scan             ⭐ the free-scan funnel
│   ├── scan/[token]/page.tsx          /scan/{token}     public result (noindex)
│   ├── rules/page.tsx                 /rules            SEO: 30 indexable pages
│   ├── rules/[ruleId]/page.tsx        /rules/s3-bucket-public-acl
│   └── trust/page.tsx                 /trust            our own security posture. Sells.
│
├── (auth)/sign-in/[[...rest]]/page.tsx        Clerk
│        sign-up/[[...rest]]/page.tsx
│
├── (dashboard)/                       ← layout.tsx: auth guard + org guard + shell
│   ├── layout.tsx
│   ├── page.tsx                       /dashboard        score, trend, top findings, accounts
│   ├── onboarding/page.tsx            /onboarding       ⭐ connect AWS (the make-or-break screen)
│   ├── findings/page.tsx              /findings         table; filters live in the URL
│   ├── findings/[id]/page.tsx         /findings/{id}    detail: explanation, fix, CLI, TF, AI
│   ├── cloud-accounts/page.tsx
│   ├── cloud-accounts/[id]/page.tsx   scan history, warnings, health
│   ├── reports/page.tsx
│   └── settings/
│       ├── team/page.tsx  billing/page.tsx  notifications/page.tsx
│       ├── suppressions/page.tsx  api-keys/page.tsx  audit-log/page.tsx
│
└── api/                               ← BFF proxy ONLY
    └── proxy/[...path]/route.ts       attach Clerk token server-side; hide the API origin
```

**Why the BFF proxy?** The browser never talks to `api.cloudguard.ai` directly. A Route Handler
attaches the Clerk session token server-side, which means (a) no token in browser-accessible JS,
(b) no CORS configuration, (c) the API origin isn't public attack surface, (d) we can add
server-side caching later without touching a component. The cost is one hop. Worth it.

## Layouts

- **Root layout** — `<ClerkProvider>`, `<QueryProvider>`, `<ThemeProvider>`, `<Toaster>`, fonts.
- **`(dashboard)/layout.tsx`** — the guard. Server-side: `auth()`; no session → redirect
  `/sign-in`; no active org → redirect to Clerk's org-creation; **no `active` cloud account →
  redirect `/onboarding`.** That last redirect is the whole product: a dashboard with no connected
  account is a dead end, and the number one reason SaaS trials die is that nobody finished setup.
  Renders sidebar + org switcher + user button.
- **`(marketing)/layout.tsx`** — public nav/footer, zero auth.

## State management — four kinds of state, four tools

The single most common frontend mistake is putting all four in one bucket (Redux/Zustand for
everything). We separate them:

| State | Tool | Example |
|---|---|---|
| **Server state** (owned by the API, cached, can go stale) | **TanStack Query** | findings, score, scans |
| **URL state** (shareable, back-button-able, survives refresh) | **`nuqs` / searchParams** | filters, sort, cursor, selected tab |
| **Ephemeral UI state** | `useState` | is this dialog open |
| **Auth/session state** | Clerk hooks | user, org, role |

**We do not add Redux or Zustand.** There is no global client state in this product that isn't one
of the four above. If a PR introduces a global store, it needs to justify itself in review.

**Filters live in the URL** (`/findings?severity=critical&status=open`), not in React state.
Consequences: a user can share "here are our criticals" in Slack, the back button works, refresh
preserves context, and E2E tests can deep-link. This is a small decision with an outsized effect on
how the product *feels*.

### TanStack Query configuration

```ts
// lib/query-keys.ts — centralised. Never inline a key string in a component.
export const qk = {
  findings: (f: FindingFilters) => ['findings', f] as const,
  finding:  (id: string)        => ['findings', id] as const,
  score:    (acct?: string)     => ['score', acct ?? 'all'] as const,
  scan:     (id: string)        => ['scans', id] as const,
  cloudAccounts:                  ['cloud-accounts'] as const,
}
```
- `staleTime: 30_000` default — findings don't change second-to-second; don't hammer the API.
- **Scan status polling:** `refetchInterval: (q) => ['queued','running'].includes(q.state.data?.status) ? 3000 : false`. Polls while it matters, stops itself when done. No `useEffect` timer to leak.
- **Optimistic updates** on suppress: update the cache immediately, roll back on error. Security
  triage is a repetitive, high-volume task; a 400ms wait per click makes the tool feel broken.
- On scan completion → `invalidateQueries(['findings'])`, `['score']`.

## Component organisation

```
components/
├── ui/                    # shadcn primitives — GENERATED, not hand-edited. Regenerable.
├── layout/                # Sidebar, TopBar, OrgSwitcher, MobileNav
├── dashboard/             # ScoreGauge, ScoreTrendChart, SeverityBreakdown, TopFindings, AccountHealth
├── findings/              # FindingsTable, FindingsFilters, SeverityBadge, FindingDetail,
│                          # RemediationTabs (Console | CLI | Terraform), EvidenceViewer,
│                          # AiContextCard, SuppressDialog, FindingTimeline
├── onboarding/            # ConnectAwsWizard, CloudFormationLaunchButton, ExternalIdReveal,
│                          # ConnectionVerifier (polls /verify), FirstScanProgress
└── shared/               # EmptyState, ErrorState, DataTable, CopyButton, MarkdownRenderer
```

**Rules:**
1. `components/ui` is shadcn's. Customise via Tailwind/CVA variants, never by editing the generated
   file — that's how you lose the ability to update it.
2. A component either **fetches** (container, uses a hook) or **renders** (presentational, takes
   props). Presentational components take no hooks and are trivially testable and Storybook-able.
3. **Colocate by feature, not by type.** `findings/` contains everything about findings.
4. **`MarkdownRenderer` must sanitise.** It renders `ai_context_md` and `remediation_md` — one of
   which is LLM output derived from attacker-controllable AWS strings. `react-markdown` +
   `rehype-sanitize`, and **never** `dangerouslySetInnerHTML`. This is a genuine XSS path; see
   [08](08-security-model.md).
5. Every list view ships three states from day one: **loading (skeleton), empty (with a CTA), and
   error (with a retry).** "Empty" is not a bug to fix later — a new user sees it first.

## Design system

Dark-mode-first (security tools are used in dark rooms and it's the genre convention). Severity is
the visual backbone and must be *consistent everywhere* — the same colour and shape in the table,
the chart, the email, and the PDF:

`CRITICAL` red-600 · `HIGH` orange-500 · `MEDIUM` amber-400 · `LOW` blue-400 · `INFO` slate-400

**Colour is never the only signal** — every severity badge carries a label and an icon. ~4% of your
male users are colour-blind, and this is exactly the kind of detail that separates a product from a
project. Charts: Recharts, with the same tokens.

## Type safety

`packages/ts-types/api.d.ts` is generated from the backend's OpenAPI schema. `lib/api-client.ts`
is a thin typed `fetch` over it. **A component cannot reference a field the API doesn't return** —
`tsc` fails, and CI regenerates the types to prove the committed file is current. This eliminates
the single most common bug class in split-stack teams.

## Performance budget

Findings table virtualised (`@tanstack/react-virtual`) — a 2,000-row account must scroll at 60fps.
Route-level code splitting by default. Charts lazy-loaded (Recharts is heavy). Lighthouse ≥ 90 on
`/` and `/pricing` — they are our funnel, and the free-scan CTA lives there.
