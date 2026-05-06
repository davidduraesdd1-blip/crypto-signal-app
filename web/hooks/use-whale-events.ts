/**
 * web/hooks/use-whale-events.ts
 * @endpoint GET /onchain/whale-events
 * Drives the On-Chain page WhaleActivity table (Everything-Live).
 */
import { useQuery } from "@tanstack/react-query";

import { getWhaleEvents } from "@/lib/api";
import { GC_TIME, queryKeys, STALE_TIME } from "@/lib/query-keys";

export function useWhaleEvents(minUsd = 10_000_000) {
  return useQuery({
    queryKey: queryKeys.whaleEvents(minUsd),
    queryFn: ({ signal }) => getWhaleEvents(minUsd, signal),
    staleTime: STALE_TIME.ONCHAIN,
    gcTime: GC_TIME.ONCHAIN,
  });
}
