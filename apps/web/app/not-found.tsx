import Link from 'next/link';

import { buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/utils';

/**
 * 404 page.
 *
 * Worth a moment of thought, because a 404 in THIS product is often not a typo.
 *
 * Our API deliberately returns 404 — never 403 — when a user requests a resource belonging to
 * ANOTHER TENANT (docs/08 § T1). A 403 would confirm the resource exists, which is an
 * enumeration oracle: an attacker could walk IDs and learn which ones are real.
 *
 * So this page is what a user sees when they follow a stale link to a finding that was
 * resolved and archived — and it is ALSO what an attacker sees when they probe for someone
 * else's data. Those two must be INDISTINGUISHABLE. No "you don't have permission to view
 * this", no different wording, no different status. The copy below is deliberately neutral.
 */
export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 px-6 text-center">
      <p className="text-6xl font-bold text-muted-foreground">404</p>
      <h1 className="text-xl font-semibold">Page not found</h1>
      <p className="max-w-md text-sm text-muted-foreground">
        This page doesn&apos;t exist, or it has moved.
      </p>
      {/* A styled link, not a button wrapping a link — see (marketing)/page.tsx. */}
      <Link href="/dashboard" className={cn(buttonVariants({ variant: 'outline' }))}>
        Back to dashboard
      </Link>
    </main>
  );
}
