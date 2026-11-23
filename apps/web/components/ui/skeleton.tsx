import type { HTMLAttributes } from 'react';

import { cn } from '@/lib/utils';

/**
 * Skeleton — the loading placeholder.
 *
 * WHY THIS EXISTS IN M0, BEFORE THERE IS ANY DATA TO LOAD
 * -------------------------------------------------------
 * docs/06 requires EVERY list view to ship three states from day one: loading, empty, error.
 * Not "loading, plus the other two later" — later never comes, and the states get bolted on
 * after a user complains.
 *
 * A skeleton that mirrors the SHAPE of the incoming content (not a centred spinner) means the
 * layout does not jump when data arrives. That layout shift is measurable (Cumulative Layout
 * Shift, a Core Web Vital) and, more importantly, it is the difference between an app that
 * feels solid and one that feels cheap. On a product asking for read access to a customer's
 * production cloud, "feels cheap" is a conversion problem.
 */
export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('animate-pulse rounded-md bg-muted', className)} {...props} />;
}
