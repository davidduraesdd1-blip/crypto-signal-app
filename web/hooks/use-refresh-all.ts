/**
 * web/hooks/use-refresh-all.ts
 *
 * Powers the global "Refresh All Data" button (every page header per
 * CLAUDE.md §12 master template requirement).
 *
 * AUDIT-2026-05-06 (post-launch v6): now exposes `pendingCount` +
 * `totalCount` so the refresh button can show a real progress
 * indicator ("3/12 done") instead of an opaque spinner. Helps the
 * user see actual refresh progress on slow Render cold-fetches.
 */
import { useIsFetching, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

export function useRefreshAll() {
  const qc = useQueryClient();
  const pendingCount = useIsFetching();
  const isFetching = pendingCount > 0;

  // Track the highest in-flight count during this refresh cycle so we
  // can compute progress = (max - pending) / max.
  const peakRef = useRef(0);
  const [peak, setPeak] = useState(0);

  useEffect(() => {
    if (pendingCount > peakRef.current) {
      peakRef.current = pendingCount;
      setPeak(pendingCount);
    }
    if (pendingCount === 0 && peakRef.current > 0) {
      // Refresh cycle finished — reset peak
      const id = setTimeout(() => {
        peakRef.current = 0;
        setPeak(0);
      }, 800); // brief delay so the "done" state is visible
      return () => clearTimeout(id);
    }
  }, [pendingCount]);

  const refresh = useCallback(() => {
    // AUDIT-2026-05-03 (D4 audit, HIGH): drop the explicit
    // refetchQueries() — invalidateQueries() ALREADY triggers a
    // refetch of every active query as part of its contract.
    qc.invalidateQueries();
  }, [qc]);

  // Progress 0..1 during a refresh cycle
  const progress = peak > 0 ? Math.max(0, Math.min(1, (peak - pendingCount) / peak)) : 1;

  return {
    refresh,
    isFetching,
    pendingCount,   // queries currently in flight
    totalCount: peak, // peak in-flight count this cycle
    progress,       // 0..1
  };
}
