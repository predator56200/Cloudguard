'use client';

import { ThemeProvider as NextThemesProvider } from 'next-themes';
import type { ComponentProps } from 'react';

/**
 * Theme provider (light / dark / system).
 *
 * Why a library rather than a `useState` and a class toggle: FLASH OF UNSTYLED CONTENT.
 * The theme lives in localStorage, which server-rendered HTML cannot read. So the page paints
 * with the DEFAULT theme, then React hydrates and swaps it — and a dark-mode user gets a
 * blinding white flash on every single page load.
 *
 * `next-themes` injects a tiny blocking script into <head> that reads localStorage and sets
 * the class BEFORE first paint. It is a fiddly problem with a boring, solved answer; we take
 * the solved answer.
 *
 * Dark-mode-first is deliberate (globals.css): security tools are used at 2am, and looking
 * like the tools our buyers already trust — Wiz, Datadog, Splunk — is itself a credibility
 * signal.
 */
export function ThemeProvider({ children, ...props }: ComponentProps<typeof NextThemesProvider>) {
  return <NextThemesProvider {...props}>{children}</NextThemesProvider>;
}
