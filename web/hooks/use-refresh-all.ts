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
    // AUDIT-2026-05-03 (D4 audit, HIGH): drop the explicit
    // refetchQueries() — invalidateQueries() ALREADY triggers a
    // refetch of every active query as part of its contract. The
    // explicit call was firing a second round of network requests
    // for every mounted query (~30 requests on a typical page).
    qc.invalidateQueries();
  }, [qc]);

  return { refresh, isFetching };
}
