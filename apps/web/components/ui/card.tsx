import type { HTMLAttributes } from 'react';

import { cn } from '@/lib/utils';

/**
 * Card — a shadcn/ui primitive. The container for every dashboard panel (score gauge,
 * severity breakdown, account health) from M5.
 *
 * Composed of small named parts (Card / CardHeader / CardTitle / CardContent) rather than one
 * component with a dozen props. Compare:
 *
 *     <Card title="Score" description="..." footer={...} headerAction={...} />   ← prop soup
 *     <Card><CardHeader><CardTitle>Score</CardTitle></CardHeader>...</Card>       ← composition
 *
 * The first design collapses the moment one panel needs a header layout nobody anticipated —
 * and then it grows a `renderHeader` escape-hatch prop and the abstraction is dead. The second
 * never has that problem, because the caller composes what they need. This is the shadcn
 * philosophy and it is correct.
 */
export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('rounded-lg border border-border bg-card text-card-foreground', className)}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('flex flex-col gap-1.5 p-6', className)} {...props} />;
}

export function CardTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  // An <h3>, not a styled <div>. Screen readers navigate by heading structure; a div with
  // big bold text is invisible to that navigation. Semantics are accessibility.
  return <h3 className={cn('font-semibold leading-none tracking-tight', className)} {...props} />;
}

export function CardDescription({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn('text-sm text-muted-foreground', className)} {...props} />;
}

export function CardContent({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('p-6 pt-0', className)} {...props} />;
}
