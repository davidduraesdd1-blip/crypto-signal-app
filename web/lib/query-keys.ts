/**
 * web/lib/query-keys.ts
 *
 * Central query-key factory. Every TanStack hook references a key from
 * here so a global "Refresh All Data" button can invalidate by prefix
 * and so per-route invalidation after mutations is consistent.
 *
 * Convention (TkDodo's recommended factory pattern):
 *   - Top-level entity name as the first segment
 *   - Filters / params follow as subsequent segments
 *   - All factories return readonly tuples for type-narrowing
 *
 * Reference: https://tkdodo.eu/blog/effective-react-query-keys
 */

import type { TradingPair } from "./api-types";

export const queryKeys = {
  // Health / system
  health: () => ["health"] as const,
  scanStatus: () => ["scan", "status"] as const,

  // Home
  homeSummary: (heroCount: number) => ["home", "summary", heroCount] as const,

  // Signals
  signals: (params?: { direction?: string; limit?: number }) =>
    ["signals", "list", params ?? {}] as const,
  signalDetail: (pair: TradingPair) =>
    ["signals", "detail", pair] as const,

  // Regimes
  regimes: () => ["regimes", "list"] as const,
  regimeHistory: (pair: TradingPair, days: number) =>
    ["regimes", "history", pair, days] as const,
  regimeTransitions: (days: number, limit: number) =>
    ["regimes", "transitions", days, limit] as const,

  // On-chain
  onchainDashboard: (pair: TradingPair) =>
    ["onchain", "dashboard", pair] as const,
  onchainMetric: (metric: string, pair: TradingPair) =>
    ["onchain", "metric", metric, pair] as const,

  // Alerts
  alertRules: () => ["alerts", "rules"] as const,
  alertLog: (limit: number) => ["alerts", "log", limit] as const,

  // AI Assistant
  aiDecisions: (limit: number, pair?: TradingPair) =>
    ["ai", "decisions", limit, pair ?? null] as const,

  // Settings
  settings: () => ["settings"] as const,

  // Diagnostics
  circuitBreakers: () => ["diagnostics", "circuit-breakers"] as const,
  databaseHealth: () => ["diagnostics", "database"] as const,

  // Execution
  executionStatus: () => ["execution", "status"] as const,

  // Backtester
  backtestSummary: () => ["backtest", "summary"] as const,
  backtestTrades: (limit: number, offset: number) =>
    ["backtest", "trades", limit, offset] as const,
  backtestRuns: () => ["backtest", "runs"] as const,
  backtestArbitrage: () => ["backtest", "arbitrage"] as const,
  optunaRuns: (n: number) => ["backtest", "optuna-runs", n] as const,
  equityCurve: () => ["backtest", "equity-curve"] as const,

  // Macro
  macroStrip: () => ["macro", "strip"] as const,

  // Regimes (extra)
  regimeWeights: () => ["regimes", "weights"] as const,
  regimeTimeline: (pair: TradingPair, days: number) =>
    ["regimes", "timeline", pair, days] as const,

  // Alerts (config)
  alertConfig: () => ["alerts", "config"] as const,

  // Agent
  agentSummary: () => ["ai", "agent", "summary"] as const,

  // Watchlist
  watchlist: (n: number) => ["home", "watchlist", n] as const,

  // Whale events
  whaleEvents: (minUsd: number) => ["onchain", "whale-events", minUsd] as const,
} as const;

// ─── Stale-time presets (per CLAUDE.md §12 cache windows) ──────────────────

export const STALE_TIME = {
  /** Live execution status — drives the AGENT pill */
  EXECUTION_STATUS: 5 * 1000,            // 5 seconds
  /** OHLCV intraday + composite signal */
  SIGNALS: 5 * 60 * 1000,                // 5 minutes
  /** Funding rates */
  FUNDING: 10 * 60 * 1000,               // 10 minutes
  /** Regime detection */
  REGIME: 15 * 60 * 1000,                // 15 minutes
  /** Alerts log */
  ALERTS_LOG: 5 * 60 * 1000,             // 5 minutes
  /** AI decisions — moderate freshness */
  AI_DECISIONS: 60 * 1000,               // 1 minute
  /** On-chain metrics */
  ONCHAIN: 60 * 60 * 1000,               // 1 hour
  /** Backtest summary / trades / runs */
  BACKTEST: 60 * 60 * 1000,              // 1 hour
  /** Fear & Greed (loaded from /home/summary) */
  FEAR_GREED: 24 * 60 * 60 * 1000,       // 24 hours
  /** Settings — invalidate on mutation, otherwise session-long */
  SETTINGS: Infinity,
  /** Diagnostics circuit breakers — moderate */
  CIRCUIT_BREAKERS: 30 * 1000,           // 30 seconds
  /** Health endpoint */
  HEALTH: 5 * 60 * 1000,                 // 5 minutes
} as const;

/** GC time = how long inactive cache survives. Default = 2× staleTime. */
export const GC_TIME = {
  EXECUTION_STATUS: 30 * 1000,
  SIGNALS: 15 * 60 * 1000,
  FUNDING: 30 * 60 * 1000,
  REGIME: 30 * 60 * 1000,
  ALERTS_LOG: 15 * 60 * 1000,
  AI_DECISIONS: 5 * 60 * 1000,
  ONCHAIN: 2 * 60 * 60 * 1000,
  BACKTEST: 2 * 60 * 60 * 1000,
  FEAR_GREED: 48 * 60 * 60 * 1000,
  SETTINGS: Infinity,
  CIRCUIT_BREAKERS: 2 * 60 * 1000,
  HEALTH: 30 * 60 * 1000,
} as const;
