/**
 * web/hooks/use-refresh-all.ts
 *
 * Powers the global "Refresh All Data" button (every page header per
 * CLAUDE.md §12 master template requirement).
 *
 * Behavior:
 *   - Stale-marks every active query
 *   - Force-refetches the queries that are currently mounted
 *   - Returns `isFetching > 0` from `useIsFetching()` so the button
 *     can show a 1.2s spinner while the refresh is in flight
 */
import { useIsFetching, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

export function useRefreshAll() {
  const qc = useQueryClient();
  const isFetching = useIsFetching() > 0;

  const refresh = useCallback(() => {
    qc.invalidateQueries();
    qc.refetchQueries({ type: "active" });
  }, [qc]);

  return { refresh, isFetching };
}
