/**
 * TanStack Query key factory.
 *
 * WHY A CENTRAL FACTORY AND NOT INLINE STRING ARRAYS
 * --------------------------------------------------
 * A query key is TanStack Query's cache identity. Inline them and this happens:
 *
 *     useQuery({ queryKey: ['findings', filters], ... })   // FindingsTable.tsx
 *     ...
 *     queryClient.invalidateQueries({ queryKey: ['finding'] })  // ← typo. SuppressDialog.tsx
 *
 * Nothing throws. Nothing goes red. The cache is simply never invalidated, so after a user
 * suppresses a finding it STAYS IN THE OPEN LIST until they hard-refresh. They conclude the
 * button is broken, and they are not wrong.
 *
 * A typed factory makes that typo a compile error. This is a five-minute file that prevents a
 * whole genre of "the UI didn't update" bug.
 *
 * HIERARCHY. Keys are structured so that a prefix invalidates everything beneath it:
 *
 *     qk.findings.all           → ['findings']
 *     qk.findings.list(filters) → ['findings', 'list', {...}]
 *     qk.findings.detail(id)    → ['findings', 'detail', id]
 *
 * After a scan completes we invalidate `qk.findings.all` and every findings list AND detail
 * refetches. That is the pattern; follow it.
 *
 * M0 ships the structure with health only. The real keys arrive with the endpoints they name.
 */
export const qk = {
  health: ['health'] as const,

  // --- M2 ---
  // cloudAccounts: {
  //   all: ['cloud-accounts'] as const,
  //   detail: (id: string) => ['cloud-accounts', 'detail', id] as const,
  // },

  // --- M4 ---
  // findings: {
  //   all: ['findings'] as const,
  //   list: (filters: FindingFilters) => ['findings', 'list', filters] as const,
  //   detail: (id: string) => ['findings', 'detail', id] as const,
  // },
  // scans:  { detail: (id: string) => ['scans', 'detail', id] as const },
  // score:  { current: (acct?: string) => ['score', acct ?? 'all'] as const },
} as const;
