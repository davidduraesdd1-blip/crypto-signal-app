/**
 * web/hooks/use-alerts.ts
 * @endpoint GET /alerts/configure
 * @endpoint POST /alerts/configure
 * @endpoint DELETE /alerts/configure/{id}
 * @endpoint GET /alerts/log
 * Drives the Alerts page (Configure list + Create + Delete) and the
 * Alerts → History page (read-only log).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createAlertRule,
  deleteAlertRule,
  getAlertLog,
  getAlertRules,
} from "@/lib/api";
import type { AlertRuleInput } from "@/lib/api-types";
import { GC_TIME, queryKeys, STALE_TIME } from "@/lib/query-keys";

export function useAlertRules() {
  return useQuery({
    queryKey: queryKeys.alertRules(),
    queryFn: ({ signal }) => getAlertRules(signal),
    staleTime: STALE_TIME.ALERTS_LOG,
    gcTime: GC_TIME.ALERTS_LOG,
  });
}

export function useAlertLog(limit = 100) {
  return useQuery({
    queryKey: queryKeys.alertLog(limit),
    queryFn: ({ signal }) => getAlertLog(limit, signal),
    staleTime: STALE_TIME.ALERTS_LOG,
    gcTime: GC_TIME.ALERTS_LOG,
  });
}

/** D4c — Create alert rule mutation. Invalidates the rules list cache
 * on success so the Configure tab refreshes immediately. */
export function useCreateAlertRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (rule: AlertRuleInput) => createAlertRule(rule),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.alertRules() });
    },
  });
}

/** D4c — Delete alert rule mutation. Optimistic UX: remove from cache
 * immediately, roll back on error. */
export function useDeleteAlertRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ruleId: string) => deleteAlertRule(ruleId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.alertRules() });
    },
  });
}
