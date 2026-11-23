import { Sidebar } from '@/components/layout/sidebar';
import { TopBar } from '@/components/layout/topbar';

/**
 * Dashboard layout — the authenticated shell.
 *
 * ⚠️ THIS FILE IS A SECURITY BOUNDARY FROM M1. Read this before you touch it.
 *
 * In M1 it becomes the guard, and it is the ONLY place these three redirects live:
 *
 *     const { userId, orgId } = await auth();
 *     if (!userId) redirect('/sign-in');           // not logged in
 *     if (!orgId)  redirect('/select-org');        // logged in, no active organisation
 *     if (!hasActiveCloudAccount) redirect('/onboarding');
 *
 * Two things about that:
 *
 * 1. IT RUNS ON THE SERVER (this is a Server Component). A client-side guard is theatre — the
 *    user can disable JS, and the data has already been sent. The server must not RENDER the
 *    page for an unauthorised user, not merely hide it. And note that even this is only the
 *    outermost layer: the API independently re-checks the caller's org on every request, and
 *    Postgres RLS independently refuses cross-tenant rows (docs/08 § four layers). A layout
 *    guard is convenience; it is never the actual protection.
 *
 * 2. THE THIRD REDIRECT IS THE PRODUCT. A dashboard with no connected AWS account is a dead
 *    end — an empty page that teaches the user nothing and quietly ends the trial. The single
 *    most common way a B2B SaaS trial dies is that nobody finished setup (docs/12 § R6).
 *    So an org with no `active` cloud account is pushed to /onboarding, always.
 *
 * The layout stays a SERVER component; only <Sidebar> and <TopBar> are client components,
 * because only they need `usePathname` and `useTheme`. Smallest possible client boundary.
 */
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar />
        {/* The main region scrolls; the shell does not. Keeps the sidebar and top bar fixed
            while a 2,000-row findings table scrolls beneath them (virtualised, from M5). */}
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
