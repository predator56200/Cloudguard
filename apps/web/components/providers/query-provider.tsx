'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';

import { ApiError } from '@/lib/api-client';

/**
 * TanStack Query provider.
 *
 * ⚠️ WHY `useState(() => new QueryClient())` AND NOT A MODULE-LEVEL `const queryClient = ...`
 * ------------------------------------------------------------------------------------------
 * This is the single most consequential line in the file, and it is a genuine security bug if
 * you get it wrong.
 *
 * A module-level QueryClient is created ONCE PER SERVER PROCESS. In the Next.js App Router,
 * components render ON THE SERVER — a process shared by every concurrent user. So a
 * module-level client would be a CACHE SHARED BETWEEN CUSTOMERS: Acme Corp's findings, cached
 * during their request, served into Globex's render.
 *
 * That is a cross-tenant data leak (docs/08 § T1) — the failure mode that ends a security
 * company — introduced by a variable declaration.
 *
 * `useState` with an initialiser creates one client PER COMPONENT INSTANCE, i.e. per request
 * on the server and once per tab in the browser. Isolated, always.
 */
export function QueryProvider({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            /**
             * 30s. Findings do not change second-to-second — a scan runs at most hourly. A
             * lower staleTime just hammers our API for data that provably has not changed.
             */
            staleTime: 30_000,

            /**
             * Do not retry a 4xx. A 401/403/404/422 is a DETERMINISTIC answer: retrying it
             * three times produces the same answer three times, more slowly, while the user
             * stares at a spinner instead of the error that would tell them what to do.
             *
             * Retry 5xx (transient), up to twice.
             */
            retry: (failureCount, error) => {
              if (error instanceof ApiError && error.status < 500) return false;
              return failureCount < 2;
            },

            // Default `true` refetches every query every time the user alt-tabs back. On a
            // dashboard someone leaves open all day, that is a lot of load for data that a
            // 30s staleTime already governs.
            refetchOnWindowFocus: false,
          },
          mutations: {
            // NEVER auto-retry a mutation. A retried POST /v1/scans could enqueue two scans.
            // Idempotency-Key (docs/05) protects the server, but the client should not be
            // firing duplicate writes on the user's behalf in the first place.
            retry: false,
          },
        },
      }),
  );

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
