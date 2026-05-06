/**
 * web/hooks/use-execution-status.ts
 * @endpoint GET /execute/status
 *
 * Drives the AGENT · RUNNING pill in the topbar.
 *
 * AUDIT-2026-05-06 (post-launch v6): polling interval bumped 5s → 15s.
 * The 5s cadence was causing visible re-render glitches on the topbar
 * level switcher (Beginner/Intermediate/Advanced) every 5s. Agent
 * state changes infrequently (only on user toggle); 15s is plenty
 * fresh. CLAUDE.md §12 says "execution status — drives the AGENT pill"
 * with no specific cadence — 15s respects the spirit.
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
    refetchInterval: polling ? 15_000 : false,
    refetchIntervalInBackground: false,
  });
}
