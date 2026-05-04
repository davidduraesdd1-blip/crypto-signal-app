/**
 * web/hooks/use-onchain-dashboard.ts
 * @endpoint GET /onchain/dashboard
 * @endpoint GET /onchain/{metric}
 * Drives the On-Chain page 3-card grid + per-tile drill-down.
 */
import { useQuery } from "@tanstack/react-query";

import { getOnchainDashboard, getOnchainMetric } from "@/lib/api";
import type { OnchainMetricKey, TradingPair } from "@/lib/api-types";
import { GC_TIME, queryKeys, STALE_TIME } from "@/lib/query-keys";

export function useOnchainDashboard(pair: TradingPair = "BTC/USDT") {
  return useQuery({
    queryKey: queryKeys.onchainDashboard(pair),
    queryFn: ({ signal }) => getOnchainDashboard(pair, signal),
    staleTime: STALE_TIME.ONCHAIN,
    gcTime: GC_TIME.ONCHAIN,
  });
}

export function useOnchainMetric(
  metric: OnchainMetricKey,
  pair: TradingPair = "BTC/USDT",
) {
  return useQuery({
    queryKey: queryKeys.onchainMetric(metric, pair),
    queryFn: ({ signal }) => getOnchainMetric(metric, pair, signal),
    staleTime: STALE_TIME.ONCHAIN,
    gcTime: GC_TIME.ONCHAIN,
  });
}
