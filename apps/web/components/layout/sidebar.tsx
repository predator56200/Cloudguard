'use client';

import { AlertTriangle, Cloud, FileText, LayoutDashboard, Settings, Shield } from 'lucide-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { cn } from '@/lib/utils';

/**
 * Dashboard sidebar.
 *
 * A CLIENT component — and for exactly one reason: `usePathname()`, to highlight the active
 * route. That is the correct instinct to develop in the App Router. Ask "what is the SMALLEST
 * thing that needs to be interactive?" and make only that a client component. The dashboard
 * layout above it stays on the server.
 *
 * The nav shape encodes the product's information architecture:
 *   Overview      → score + trend. The "how are we doing?" screen.
 *   Findings      → the triage queue. Where a user actually spends their time.
 *   AWS Accounts  → connection health. Where they go when something breaks.
 *   Reports       → the weekly PDF. What they forward to their CEO.
 *   Settings      → team, billing, suppressions, audit log.
 *
 * Everything here is M0 scaffolding: the routes exist, the pages say "coming in Mx". Building
 * the shell first means every later milestone lands INTO a structure instead of inventing one.
 */
const NAV = [
  { href: '/dashboard', label: 'Overview', icon: LayoutDashboard, milestone: 'M5' },
  { href: '/dashboard/findings', label: 'Findings', icon: AlertTriangle, milestone: 'M5' },
  { href: '/dashboard/cloud-accounts', label: 'AWS Accounts', icon: Cloud, milestone: 'M2' },
  { href: '/dashboard/reports', label: 'Reports', icon: FileText, milestone: 'M7' },
  { href: '/dashboard/settings', label: 'Settings', icon: Settings, milestone: 'M8' },
] as const;

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden w-60 shrink-0 border-r border-border bg-card md:flex md:flex-col">
      <div className="flex h-14 items-center gap-2 border-b border-border px-6">
        <Shield className="h-5 w-5 text-primary" aria-hidden="true" />
        <span className="font-semibold">CloudGuard</span>
      </div>

      {/* <nav> + aria-current: a screen-reader user needs to know this is navigation and
          which item is current. A <div> full of links tells them neither. */}
      <nav className="flex flex-1 flex-col gap-1 p-3" aria-label="Main navigation">
        {NAV.map(({ href, label, icon: Icon }) => {
          // Exact match for the index route, prefix match for the rest — otherwise /dashboard
          // would light up for every child page.
          const isActive = href === '/dashboard' ? pathname === href : pathname.startsWith(href);

          return (
            <Link
              key={href}
              href={href}
              aria-current={isActive ? 'page' : undefined}
              className={cn(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-muted text-foreground'
                  : 'text-muted-foreground hover:bg-muted hover:text-foreground',
              )}
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-border p-3 text-xs text-muted-foreground">
        M0 · Foundations
      </div>
    </aside>
  );
}
