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
    // While a scan is running, refresh status every 5s so the
    // progress bar updates. Otherwise, the §12 5-min stale-time
    // applies and we don't poll.
    refetchInterval: polling ? 5_000 : false,
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
