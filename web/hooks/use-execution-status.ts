/**
 * web/hooks/use-execution-status.ts
 * @endpoint GET /execute/status
 *
 * Drives the AGENT · RUNNING pill in the topbar — polls every 5s to
 * keep the live indicator current. Per CLAUDE.md §12 cache window for
 * "execution status" + D4 plan §5.
 *
 * Also used inside the AI Assistant page for the cycle counter.
 */
import { useQuery } from "@tanstack/react-query";

import { getExecutionStatus } from "@/lib/api";
import { GC_TIME, queryKeys, STALE_TIME } from "@/lib/query-keys";

export function useExecutionStatus(options: { polling?: boolean } = {}) {
  const { polling = true } = options;
  return useQuery({
    queryKey: queryKeys.executionStatus(),
    queryFn: ({ signal }) => getExecutionStatus(signal),
    staleTime: STALE_TIME.EXECUTION_STATUS,
    gcTime: GC_TIME.EXECUTION_STATUS,
    refetchInterval: polling ? 5_000 : false,
    refetchIntervalInBackground: false,
  });
}
