import type { Metadata } from 'next';
import { Inter } from 'next/font/google';

import { Providers } from '@/components/providers';

import './globals.css';

/**
 * Root layout — wraps EVERY page (marketing, auth, dashboard).
 *
 * This is a SERVER COMPONENT. Note there is no `'use client'` here, and that is load-bearing:
 * `'use client'` is a BOUNDARY, not a file flag — everything imported beneath it becomes
 * client code too. Marking the root layout as a client component would ship the entire
 * application to the browser and forfeit server rendering everywhere. All the client-side
 * context we need is isolated inside <Providers> (components/providers/index.tsx).
 *
 * `next/font` self-hosts Inter at build time. It does NOT hit fonts.googleapis.com at runtime.
 * Two reasons that matters: (1) speed — no extra DNS + TLS handshake on first paint; (2) a
 * request to a Google CDN on every page load of a SECURITY dashboard is a privacy leak we
 * would have to explain in our own DPA, and "we don't do that" is a much better answer than
 * a paragraph of justification.
 */
const inter = Inter({ subsets: ['latin'], variable: '--font-sans' });

export const metadata: Metadata = {
  title: {
    default: 'CloudGuard AI — Cloud security that fixes itself',
    // Every page below gets "· CloudGuard AI" appended automatically.
    template: '%s · CloudGuard AI',
  },
  description:
    'AI-powered AWS security for startups. Connect AWS and GitHub; we send pull requests, not alerts.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // suppressHydrationWarning is REQUIRED on <html> when using next-themes: the theme script
    // mutates the class attribute before React hydrates, which React would otherwise report as
    // a mismatch. This is the one sanctioned use of it — do not sprinkle it elsewhere to
    // silence real hydration bugs.
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.variable} font-sans antialiased`}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
