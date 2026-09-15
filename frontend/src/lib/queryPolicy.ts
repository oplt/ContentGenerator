/**
 * Frontend query freshness classes (Phase 7.3).
 *
 * Nearly static — catalogs, app config, capability metadata
 * Moderate — settings, source config, account lists
 * Fast — job status, publishing, generation progress (pair with statusAwareRefetchInterval)
 */
export const queryPolicy = {
  static: {
    staleTime: 60 * 60_000,
    gcTime: 6 * 60 * 60_000,
  },
  moderate: {
    staleTime: 5 * 60_000,
    gcTime: 30 * 60_000,
  },
  /** Health summaries: show cached, refresh explicitly or when stale. */
  health: {
    staleTime: 10 * 60_000,
    gcTime: 60 * 60_000,
  },
  fast: {
    staleTime: 15_000,
    gcTime: 5 * 60_000,
  },
} as const;

export type QueryPolicyName = keyof typeof queryPolicy;
