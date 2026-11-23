'use client';

import { Moon, Sun } from 'lucide-react';
import { useTheme } from 'next-themes';
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';

/**
 * Dashboard top bar.
 *
 * M1 adds Clerk's <OrganizationSwitcher /> and <UserButton /> here — the org switcher is the
 * visible surface of our multi-tenancy, and it matters more than it looks: consultants and
 * MSPs belong to several orgs at once, which is why `users` is a GLOBAL table in our schema
 * rather than a child of `organizations` (docs/04).
 *
 * ⚠️ THE `mounted` DANCE BELOW IS NOT SUPERSTITION.
 * `useTheme()` reads localStorage, which does not exist on the server. So the server renders
 * (say) the Moon icon while the client renders the Sun — React sees a mismatch and throws a
 * hydration error, which in production degrades to a full client re-render of the subtree.
 *
 * Rendering a placeholder until `mounted` is true is the standard fix: it makes the FIRST
 * client render identical to the server's, and only then swaps in the real, storage-dependent
 * UI. Any component whose output depends on browser-only state needs this pattern.
 */
export function TopBar() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border px-6">
      <div className="text-sm text-muted-foreground">
        {/* M1: <OrganizationSwitcher /> */}
        CloudGuard AI
      </div>

      <div className="flex items-center gap-2">
        {mounted ? (
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            // An icon-only button is unlabelled to a screen reader — it announces as
            // "button", which is useless. aria-label is not optional here.
            aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          >
            {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
        ) : (
          // Same dimensions as the button, so nothing shifts when it swaps in.
          <div className="h-9 w-9" />
        )}

        {/* M1: <UserButton /> */}
      </div>
    </header>
  );
}
