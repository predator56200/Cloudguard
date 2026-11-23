import Link from 'next/link';

import { Button, buttonVariants } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { cn } from '@/lib/utils';

/**
 * Landing page — `/`.
 *
 * A SERVER COMPONENT, statically generated. Zero JavaScript is shipped for it.
 *
 * That is not a micro-optimisation, it is the growth strategy (docs/09 § M8): `/` and
 * `/pricing` are the top of the free-scan funnel, and `/rules` will be 30 indexable pages of
 * genuine security content — our organic acquisition channel. A slow, JS-heavy landing page
 * is a page Google ranks lower and visitors bounce from before the CTA renders.
 *
 * Route groups: `(marketing)` does not appear in the URL. It exists so this page and the
 * dashboard can have COMPLETELY DIFFERENT LAYOUTS while sharing the root layout. `(marketing)`
 * gets a public nav; `(dashboard)` gets an auth guard and a sidebar. Without route groups you
 * would be putting `if (isDashboard)` branches in a shared layout, which rots immediately.
 */
export default function LandingPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col items-center justify-center px-6 py-24 text-center">
      <p className="border-border text-muted-foreground mb-4 rounded-full border px-3 py-1 text-xs">
        M0 · Foundations
      </p>

      <h1 className="max-w-3xl text-5xl font-bold tracking-tight">
        Cloud security that <span className="text-primary">fixes itself</span>
      </h1>

      <p className="text-muted-foreground mt-6 max-w-2xl text-lg">
        Connect AWS and GitHub. CloudGuard finds the misconfiguration, traces it back to the
        Terraform that created it, and opens a pull request. We send fixes, not alerts.
      </p>

      <div className="mt-10 flex gap-3">
        {/* The free instant scan is the entire top of the acquisition funnel (docs/09 § M8).
            It is wired in M8; the CTA exists now so the page it lands on is never an
            afterthought. */}
        <Button size="lg" disabled>
          Scan my AWS account free — M8
        </Button>

        {/* A LINK styled as a button — not a <Button> wrapping a <Link>.
            That nesting produces `<button><a>…</a></button>`, which is invalid HTML: a button
            is not permitted to contain interactive content. Browsers "handle" it, but keyboard
            and screen-reader behaviour becomes genuinely unpredictable (two focusable elements,
            one visual control).
            Navigation is an <a>. Actions are a <button>. `buttonVariants` lets a link BORROW the
            styling without borrowing the wrong semantics — this is the shadcn pattern, and it
            exists precisely because people get this wrong. */}
        <Link
          href="/dashboard"
          className={cn(buttonVariants({ variant: 'outline', size: 'lg' }))}
        >
          View the dashboard
        </Link>
      </div>

      <div className="mt-20 grid w-full gap-4 text-left sm:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Read-only, always</CardTitle>
            <CardDescription>Cross-account IAM role. No access keys.</CardDescription>
          </CardHeader>
          <CardContent className="text-muted-foreground text-sm">
            SecurityAudit + ViewOnlyAccess. We are structurally incapable of writing to your
            cloud — revoke us with one click, in your own console.
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">30 rules, not 600</CardTitle>
            <CardDescription>Signal, not a longer list.</CardDescription>
          </CardHeader>
          <CardContent className="text-muted-foreground text-sm">
            Ranked by whether the resource is actually reachable and actually production — not
            by a generic severity label.
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Fixes that merge</CardTitle>
            <CardDescription>The metric is PRs merged.</CardDescription>
          </CardHeader>
          <CardContent className="text-muted-foreground text-sm">
            A findings list nobody acts on is a report. We measure ourselves on issues actually
            closed.
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
