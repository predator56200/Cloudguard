'use client';

import type { ReactNode } from 'react';

import { QueryProvider } from '@/components/providers/query-provider';
import { ThemeProvider } from '@/components/providers/theme-provider';

/**
 * All client-side providers, composed once.
 *
 * Why a single `<Providers>` rather than nesting four providers in the root layout: the root
 * layout stays a SERVER COMPONENT. Providers need `'use client'` (they use hooks and React
 * context); if we put them directly in layout.tsx, the entire layout — and with it every page
 * beneath it — becomes a client component, and we lose server rendering for the whole app.
 *
 * Isolating them in one client boundary keeps the tree above it on the server. This is the
 * standard App Router pattern and the reason it exists is worth understanding: `'use client'`
 * is a BOUNDARY, not a file-level flag — everything imported below it is client code too.
 *
 * M1 wraps ClerkProvider around these.
 */
export function Providers({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="dark" enableSystem>
      <QueryProvider>{children}</QueryProvider>
    </ThemeProvider>
  );
}
