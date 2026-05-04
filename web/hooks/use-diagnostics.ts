/**
 * web/hooks/use-diagnostics.ts
 * @endpoint GET /diagnostics/circuit-breakers
 * @endpoint GET /diagnostics/database
 * @endpoint GET /health (public, no API key needed)
 * Drives Settings · Dev Tools (7-gate card + 5-col KPI strip).
 */
import { useQuery } from "@tanstack/react-query";

import { getCircuitBreakers, getDatabaseHealth, getHealth } from "@/lib/api";
import { GC_TIME, queryKeys, STALE_TIME } from "@/lib/query-keys";

export function useCircuitBreakers() {
  return useQuery({
    queryKey: queryKeys.circuitBreakers(),
    queryFn: ({ signal }) => getCircuitBreakers(signal),
    staleTime: STALE_TIME.CIRCUIT_BREAKERS,
    gcTime: GC_TIME.CIRCUIT_BREAKERS,
  });
}

export function useDatabaseHealth() {
  return useQuery({
    queryKey: queryKeys.databaseHealth(),
    queryFn: ({ signal }) => getDatabaseHealth(signal),
    staleTime: STALE_TIME.HEALTH,
    gcTime: GC_TIME.HEALTH,
  });
}

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health(),
    queryFn: ({ signal }) => getHealth(signal),
    staleTime: STALE_TIME.HEALTH,
    gcTime: GC_TIME.HEALTH,
  });
}
