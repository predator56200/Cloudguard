import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

/**
 * Loading UI — `/dashboard`.
 *
 * The App Router wires this up automatically: Next wraps the route in a React <Suspense>
 * boundary with THIS as the fallback. No `isLoading` state, no ternary in the page component.
 *
 * WHY IT SHIPS IN M0, WITH NOTHING TO LOAD
 * ----------------------------------------
 * docs/06 requires every view to have loading / empty / error states FROM DAY ONE. States
 * added "later", after a user complains, are states that were designed under pressure.
 *
 * And note the shape: this skeleton MIRRORS the real layout — three cards in a row, same
 * heights. A centred spinner would let the page jump when data lands. That jump is a measured
 * Core Web Vital (Cumulative Layout Shift), but more importantly it is the difference between
 * an app that feels solid and one that feels cheap — and we are asking people to hand us read
 * access to their production cloud.
 */
export default function DashboardLoading() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-4 w-64" />
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <Card key={i}>
            <CardHeader>
              <Skeleton className="h-5 w-32" />
              <Skeleton className="h-3 w-20" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-10 w-16" />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
