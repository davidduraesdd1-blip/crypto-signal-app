/**
 * web/hooks/use-alerts-config.ts
 * @endpoints GET /alerts/config, PUT /alerts/config
 * Drives the Alerts page configure tab (Everything-Live).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getAlertConfig,
  putAlertConfig,
  type AlertConfigPatchInput,
  type AlertConfigResponse,
} from "@/lib/api";
import { GC_TIME, queryKeys, STALE_TIME } from "@/lib/query-keys";

export function useAlertConfig() {
  return useQuery({
    queryKey: queryKeys.alertConfig(),
    queryFn: ({ signal }) => getAlertConfig(signal),
    staleTime: STALE_TIME.SETTINGS,
    gcTime: GC_TIME.SETTINGS,
  });
}

export function useUpdateAlertConfig() {
  const qc = useQueryClient();
  return useMutation<AlertConfigResponse, Error, AlertConfigPatchInput>({
    mutationFn: putAlertConfig,
    onSuccess: (data) => {
      qc.setQueryData(queryKeys.alertConfig(), data);
    },
  });
}
