/**
 * web/hooks/use-watchlist.ts
 * @endpoint GET /home/watchlist
 * Drives the Home Watchlist (Everything-Live).
 */
import { useQuery } from "@tanstack/react-query";

import { getWatchlist } from "@/lib/api";
import { GC_TIME, queryKeys, STALE_TIME } from "@/lib/query-keys";

export function useWatchlist(n = 6, sparklineN = 24) {
  return useQuery({
    queryKey: queryKeys.watchlist(n),
    queryFn: ({ signal }) => getWatchlist(n, sparklineN, signal),
    staleTime: STALE_TIME.SIGNALS,
    gcTime: GC_TIME.SIGNALS,
  });
}
