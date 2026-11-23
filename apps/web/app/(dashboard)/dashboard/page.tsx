import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

/**
 * Dashboard overview — `/dashboard`.
 *
 * M0 scaffolding. In M5 this becomes the product's front door: security score gauge, 90-day
 * trend chart (fed by the pre-aggregated `score_snapshots` table — one indexed range scan,
 * not an aggregate over millions of finding rows), severity breakdown, top findings, and
 * account health.
 *
 * It renders NOW, with honest placeholders, for a reason worth stating: the shell is built
 * before the features so that every later milestone lands INTO a structure. The alternative —
 * inventing the layout while also building the score chart — is how you end up with five
 * pages that each look like a different product.
 */
export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Overview</h1>
        <p className="text-sm text-muted-foreground">
          Your AWS security posture at a glance.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Security score</CardTitle>
            <CardDescription>Arrives in M5</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-4xl font-bold text-muted-foreground">—</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Open findings</CardTitle>
            <CardDescription>Arrives in M4</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-4xl font-bold text-muted-foreground">—</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">AWS accounts</CardTitle>
            <CardDescription>Arrives in M2</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-4xl font-bold text-muted-foreground">—</div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">M0 · Foundations complete</CardTitle>
          <CardDescription>
            Monorepo, Docker, FastAPI, ARQ worker, Postgres, Redis, Alembic, CI, and this
            shell. No business logic — by design.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Next: <strong className="text-foreground">M1 — Auth &amp; Tenancy</strong>. Clerk
          organisations, PostgreSQL Row-Level Security, and the evil-tenant test suite that
          proves two organisations cannot see each other&apos;s data.
        </CardContent>
      </Card>
    </div>
  );
}
