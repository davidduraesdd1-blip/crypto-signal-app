/**
 * web/hooks/use-backtester.ts
 * @endpoint GET /backtest/summary
 * @endpoint GET /backtest/trades
 * @endpoint GET /backtest/runs
 * @endpoint GET /backtest/arbitrage
 * Drives the Backtester page (summary KPIs + trade table) and the
 * Arbitrage sub-tab.
 */
import { useQuery } from "@tanstack/react-query";

import {
  getBacktestArbitrage,
  getBacktestRuns,
  getBacktestSummary,
  getBacktestTrades,
  getOptunaRuns,
  getEquityCurve,
} from "@/lib/api";
import { GC_TIME, queryKeys, STALE_TIME } from "@/lib/query-keys";

export function useBacktestSummary() {
  return useQuery({
    queryKey: queryKeys.backtestSummary(),
    queryFn: ({ signal }) => getBacktestSummary(signal),
    staleTime: STALE_TIME.BACKTEST,
    gcTime: GC_TIME.BACKTEST,
  });
}

export function useBacktestTrades(limit = 50, offset = 0) {
  return useQuery({
    queryKey: queryKeys.backtestTrades(limit, offset),
    queryFn: ({ signal }) => getBacktestTrades(limit, offset, signal),
    staleTime: STALE_TIME.BACKTEST,
    gcTime: GC_TIME.BACKTEST,
  });
}

export function useBacktestRuns() {
  return useQuery({
    queryKey: queryKeys.backtestRuns(),
    queryFn: ({ signal }) => getBacktestRuns(signal),
    staleTime: STALE_TIME.BACKTEST,
    gcTime: GC_TIME.BACKTEST,
  });
}

export function useBacktestArbitrage() {
  return useQuery({
    queryKey: queryKeys.backtestArbitrage(),
    queryFn: ({ signal }) => getBacktestArbitrage(signal),
    staleTime: STALE_TIME.BACKTEST,
    gcTime: GC_TIME.BACKTEST,
  });
}

export function useOptunaRuns(n = 10) {
  return useQuery({
    queryKey: queryKeys.optunaRuns(n),
    queryFn: ({ signal }) => getOptunaRuns(n, signal),
    staleTime: STALE_TIME.BACKTEST,
    gcTime: GC_TIME.BACKTEST,
  });
}

export function useEquityCurve() {
  return useQuery({
    queryKey: queryKeys.equityCurve(),
    queryFn: ({ signal }) => getEquityCurve(signal),
    staleTime: STALE_TIME.BACKTEST,
    gcTime: GC_TIME.BACKTEST,
  });
}
