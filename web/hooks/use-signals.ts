/**
 * web/hooks/use-signals.ts
 * @endpoint GET /signals
 * @endpoint GET /signals/{pair}
 * Drives the Signals page list + detail panel.
 */
import { useQuery } from "@tanstack/react-query";

import { getSignals, getSignalForPair, type GetSignalsParams } from "@/lib/api";
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
