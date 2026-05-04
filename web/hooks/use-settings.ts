/**
 * web/hooks/use-settings.ts
 * @endpoint GET /settings/
 * @endpoint PUT /settings/{group}
 * Drives all 4 Settings sub-pages (Trading, Signal-Risk, Dev-Tools,
 * Execution). The GET is shared across all 4; mutations are per-group.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getSettings, putSettings, type SettingsGroup } from "@/lib/api";
import type { SettingsPatch } from "@/lib/api-types";
import { GC_TIME, queryKeys, STALE_TIME } from "@/lib/query-keys";

export function useSettings() {
  return useQuery({
    queryKey: queryKeys.settings(),
    queryFn: ({ signal }) => getSettings(signal),
    staleTime: STALE_TIME.SETTINGS,
    gcTime: GC_TIME.SETTINGS,
  });
}

/** D4c — Save a settings group. Invalidates the snapshot on success
 * so all 4 sub-pages reflect the new values immediately. The response
 * surfaces a `rejected: [{key, reason, value}]` array when type/range
 * validation drops a value (per the P-19 settings PUT validation
 * shipped 2026-05-03 in commit ff02657). Callers should display
 * `data.rejected` as inline errors next to the offending fields. */
export function useSaveSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ group, patch }: { group: SettingsGroup; patch: SettingsPatch }) =>
      putSettings(group, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.settings() });
    },
  });
}
