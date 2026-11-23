'use client';

import { AlertTriangle } from 'lucide-react';
import { useEffect } from 'react';

import { Button } from '@/components/ui/button';

/**
 * Error boundary for the whole dashboard segment.
 *
 * MUST be a client component — React error boundaries rely on class-component lifecycle,
 * which only exists on the client. Next wires this file up automatically for the segment.
 *
 * ⚠️ SECURITY: NEVER RENDER `error.message`.
 * ------------------------------------------
 * That message can contain anything an exception carried: an internal URL, a stack frame, a
 * database error naming a table, a fragment of a payload. Our BACKEND already refuses to leak
 * internals (apps/api/.../error_handler.py returns a generic 500) — it would be absurd to
 * spend that effort and then print the frontend's raw exception into the page of a security
 * dashboard.
 *
 * The user gets a plain message and a `digest` — a hash Next generates that correlates to the
 * full error in OUR server logs. Exactly the same trade as the backend's `request_id`: the
 * user gets an identifier, we get the detail.
 */
export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // M8: report to Sentry here. Deliberately not `console.log(error)` — see above.
    // eslint-disable-next-line no-console
    console.error('Dashboard error:', error.digest);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 text-center">
      <AlertTriangle className="h-10 w-10 text-destructive" aria-hidden="true" />

      <div>
        <h2 className="text-lg font-semibold">Something went wrong</h2>
        <p className="mt-1 max-w-md text-sm text-muted-foreground">
          We hit an unexpected error loading this page. The team has been notified.
        </p>
      </div>

      {/* Give support something to search on. Same idea as X-Request-ID on the API. */}
      {error.digest && (
        <code className="rounded bg-muted px-2 py-1 text-xs text-muted-foreground">
          Reference: {error.digest}
        </code>
      )}

      {/* `reset()` re-renders the segment without a full page reload — so a transient failure
          (an API blip) recovers in place, keeping the user's scroll position and filters. */}
      <Button onClick={reset} variant="outline">
        Try again
      </Button>
    </div>
  );
}
