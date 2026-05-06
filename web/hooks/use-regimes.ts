/**
 * web/hooks/use-regimes.ts
 * @endpoint GET /regimes/
 * @endpoint GET /regimes/{pair}/history
 * @endpoint GET /regimes/transitions
 * Drives the Regimes page main list + per-pair history + transitions.
 */
import { useQuery } from "@tanstack/react-query";

import {
  getRegimeHistory,
  getRegimes,
  getRegimeTransitions,
  getRegimeWeights,
  getRegimeTimeline,
} from "@/lib/api";
import type { TradingPair } from "@/lib/api-types";
import { GC_TIME, queryKeys, STALE_TIME } from "@/lib/query-keys";

export function useRegimes() {
  return useQuery({
    queryKey: queryKeys.regimes(),
    queryFn: ({ signal }) => getRegimes(signal),
    staleTime: STALE_TIME.REGIME,
    gcTime: GC_TIME.REGIME,
  });
}

export function useRegimeHistory(pair: TradingPair | null, days = 90) {
  return useQuery({
    queryKey: queryKeys.regimeHistory(pair ?? "", days),
    queryFn: ({ signal }) => getRegimeHistory(pair as TradingPair, days, signal),
    enabled: !!pair,
    staleTime: STALE_TIME.REGIME,
    gcTime: GC_TIME.REGIME,
  });
}

export function useRegimeTransitions(days = 30, limit = 200) {
  return useQuery({
    queryKey: queryKeys.regimeTransitions(days, limit),
    queryFn: ({ signal }) => getRegimeTransitions(days, limit, signal),
    staleTime: STALE_TIME.REGIME,
    gcTime: GC_TIME.REGIME,
  });
}

export function useRegimeWeights() {
  return useQuery({
    queryKey: queryKeys.regimeWeights(),
    queryFn: ({ signal }) => getRegimeWeights(signal),
    staleTime: STALE_TIME.REGIME,
    gcTime: GC_TIME.REGIME,
  });
}

export function useRegimeTimeline(pair: TradingPair | null, days = 90) {
  return useQuery({
    queryKey: queryKeys.regimeTimeline(pair ?? "", days),
    queryFn: ({ signal }) => getRegimeTimeline(pair as TradingPair, days, signal),
    enabled: !!pair,
    staleTime: STALE_TIME.REGIME,
    gcTime: GC_TIME.REGIME,
  });
}
