/**
 * web/hooks/use-home-summary.ts
 * @endpoint GET /home/summary
 * Drives the Home page hero cards + info strip.
 */
import { useQuery } from "@tanstack/react-query";

import { getHomeSummary } from "@/lib/api";
import { GC_TIME, queryKeys, STALE_TIME } from "@/lib/query-keys";

export function useHomeSummary(heroCount = 5) {
  return useQuery({
    queryKey: queryKeys.homeSummary(heroCount),
    queryFn: ({ signal }) => getHomeSummary(heroCount, signal),
    staleTime: STALE_TIME.SIGNALS,
    gcTime: GC_TIME.SIGNALS,
  });
}
