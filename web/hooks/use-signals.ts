/**
 * web/hooks/use-signals.ts
 * @endpoint GET /signals
 * @endpoint GET /signals/{pair}
 * @endpoint GET /signals/history?pair={pair}
 * Drives the Signals page list + detail panel + recent transitions.
 */
import { useQuery } from "@tanstack/react-query";

import {
  getSignals,
  getSignalForPair,
  getSignalHistory,
  type GetSignalsParams,
} from "@/lib/api";
import type { TradingPair } from "@/lib/api-types";
import { GC_TIME, queryKeys, STALE_TIME } from "@/lib/query-keys";

export function useSignals(params: GetSignalsParams = {}) {
  return useQuery({
    queryKey: queryKeys.signals(params),
    queryFn: ({ signal }) => getSignals(params, signal),
    staleTime: STALE_TIME.SIGNALS,
    gcTime: GC_TIME.SIGNALS,
  });
}

export function useSignalDetail(pair: TradingPair | null) {
  return useQuery({
    queryKey: queryKeys.signalDetail(pair ?? ""),
    queryFn: ({ signal }) => getSignalForPair(pair as TradingPair, signal),
    enabled: !!pair,
    staleTime: STALE_TIME.SIGNALS,
    gcTime: GC_TIME.SIGNALS,
  });
}

// AUDIT-2026-05-05 (P0-7): replace v0 mock signal-history block on the
// Signals page. Wires /signals/history?pair=X to the daily_signals DB
// table. Limit 50 because we filter to direction transitions client-
// side; consecutive same-direction rows collapse to one entry.
export function useSignalHistory(pair: TradingPair | null, limit = 50) {
  return useQuery({
    queryKey: ["signals", "history", pair ?? "", limit] as const,
    queryFn: ({ signal }) => getSignalHistory(pair as TradingPair, limit, signal),
    enabled: !!pair,
    staleTime: STALE_TIME.SIGNALS,
    gcTime: GC_TIME.SIGNALS,
  });
}
