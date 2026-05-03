/**
 * web/hooks/use-scan.ts
 * @endpoint GET /scan/status
 * @endpoint POST /scan/trigger
 * Scan-status indicator on Home + the global "Refresh All Data" button
 * also calls trigger when on the Signals page.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getScanStatus, triggerScan } from "@/lib/api";
import { GC_TIME, queryKeys, STALE_TIME } from "@/lib/query-keys";

export function useScanStatus(options: { polling?: boolean } = {}) {
  const { polling = true } = options;
  return useQuery({
    queryKey: queryKeys.scanStatus(),
    queryFn: ({ signal }) => getScanStatus(signal),
    staleTime: STALE_TIME.SIGNALS,
    gcTime: GC_TIME.SIGNALS,
    // AUDIT-2026-05-03 (D4 audit, MEDIUM): adaptive polling — only
    // re-fetch every 5s while a scan is actually running. Otherwise
    // honor the §12 5-min stale-time and don't poll. Without this,
    // every page mounting a scan-status hook burned 720 requests/hour
    // even when no scan was active.
    refetchInterval: polling
      ? (query) => (query.state.data?.running ? 5_000 : false)
      : false,
  });
}

/** D4c — Trigger a fresh scan. Invalidates everything signal-related
 * (signals list + home summary + scan status) on success. */
export function useTriggerScan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => triggerScan(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["signals"] });
      qc.invalidateQueries({ queryKey: ["home"] });
      qc.invalidateQueries({ queryKey: queryKeys.scanStatus() });
    },
  });
}
