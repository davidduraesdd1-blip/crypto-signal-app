/**
 * web/lib/query-client.ts
 *
 * TanStack Query v5 client + sensible defaults.
 *
 * Defaults rationale (D4 plan §5):
 *   - retry: 1   — one retry catches transient network blips without
 *                  hiding actual API errors behind 3-retry jitter
 *   - retryDelay: exponential with 30s ceiling — handles Render
 *                  cold-start without hammering on a real outage
 *   - refetchOnWindowFocus: false — the AGENT pill polls actively;
 *                  on-focus refetch would double-fire on every alt-tab
 *   - refetchOnReconnect: true — network-restoration refetch is
 *                  always desirable
 *   - staleTime / gcTime: per-hook via STALE_TIME / GC_TIME presets
 *                  in query-keys.ts; this file's defaults apply only
 *                  to hooks that don't override
 */
import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "./api";

/** Used by both client and SSR HydrationBoundary paths. */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Conservative default — most queries override via STALE_TIME presets
        staleTime: 60 * 1000,
        gcTime: 5 * 60 * 1000,
        retry: (failureCount, err) => {
          // Don't retry auth errors — the user needs to fix the key
          if (err instanceof ApiError && err.isAuthError) return false;
          // Don't retry 4xx (except 408 timeout / 429 rate-limit)
          if (err instanceof ApiError) {
            if (err.status === 408 || err.status === 429) {
              return failureCount < 2;
            }
            if (err.status >= 400 && err.status < 500) return false;
          }
          // Retry up to 1 extra time for network / 5xx
          return failureCount < 1;
        },
        retryDelay: (attemptIndex) =>
          Math.min(1000 * 2 ** attemptIndex, 30 * 1000),
        refetchOnWindowFocus: false,
        refetchOnReconnect: true,
      },
      mutations: {
        retry: 0,
      },
    },
  });
}
