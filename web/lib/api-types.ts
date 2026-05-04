/**
 * web/lib/api-types.ts
 *
 * Manual TypeScript types mirroring the FastAPI Pydantic response shapes.
 * Each type carries an `// @endpoint <route>` JSDoc tag so grep finds
 * the consumer when the Python-side Pydantic model changes. The
 * contract test in `web/tests/api-contract.test.ts` (D4d) asserts
 * these names exist in the live deploy's `/openapi.json`.
 *
 * Source-of-truth Python files for reference:
 *   - api.py                (legacy /signals, /scan, /execute, /health)
 *   - routers/home.py       (/home/summary)
 *   - routers/regimes.py    (/regimes/*)
 *   - routers/onchain.py    (/onchain/*)
 *   - routers/alerts.py     (/alerts/configure)
 *   - routers/ai_assistant.py (/ai/*)
 *   - routers/settings.py   (/settings/*)
 *   - routers/exchange.py   (/exchange/test-connection)
 *   - routers/diagnostics.py (/diagnostics/*)
 *
 * Drift policy (D4 plan §4): if a Pydantic model changes, update the
 * corresponding type here AND its consumer hook AND the contract test.
 */

// ─── Common scalars ─────────────────────────────────────────────────────────

/** ISO-8601 UTC timestamp (e.g. "2026-05-03T15:54:35.985949+00:00") */
export type IsoTimestamp = string;

/** Trading pair in canonical "BASE/QUOTE" form (e.g. "BTC/USDT") */
export type TradingPair = string;

/** Direction labels emitted by the engine (per CLAUDE.md §9) */
export type DirectionLabel =
  | "BUY"
  | "SELL"
  | "STRONG BUY"
  | "STRONG SELL"
  | "NEUTRAL"
  | "HOLD";

/** Regime label set per CLAUDE.md §9 + legacy fallback shim */
export type RegimeLabel =
  | "Bull"
  | "Bear"
  | "Sideways"
  | "Transition"
  | "Trending"
  | "Ranging"
  | "Neutral"
  | "Unknown"
  | string; // engine may emit a new state — we display verbatim

// ─── Scan results / signals ─────────────────────────────────────────────────

/**
 * @endpoint GET /signals (one row of the array)
 * @endpoint GET /signals/{pair}
 * Mirrors crypto_model_core scan output rows persisted via
 * db.write_scan_results.
 */
export interface SignalRow {
  pair: TradingPair;
  direction: DirectionLabel | string;
  confidence_avg_pct: number | null;
  regime?: RegimeLabel | null;
  regime_label?: RegimeLabel | null;
  high_conf?: boolean;
  price?: number | null;
  price_usd?: number | null;
  change_24h_pct?: number | null;
  mtf_alignment?: number | null;
  risk_mode?: string | null;
  entry?: number | null;
  stop_loss?: number | null;
  exit?: number | null;
  position_size_pct?: number | null;
  // Optional indicator snapshot fields used by /signals/{pair} detail
  rsi?: number | null;
  adx?: number | null;
  macd?: number | null;
  // Catch-all for additional engine-emitted fields the frontend may
  // surface in a future polish pass.
  [extra: string]: unknown;
}

/** @endpoint GET /signals — wrapped list response */
export interface SignalsList {
  count: number;
  results: SignalRow[];
}

// ─── Home aggregation ───────────────────────────────────────────────────────

/** @endpoint GET /home/summary — one hero card */
export interface HeroCard {
  pair: TradingPair;
  direction: DirectionLabel | string | null;
  confidence: number | null;
  regime: RegimeLabel | null;
  high_conf: boolean;
  price: number | null;
  change_24h: number | null;
}

/** @endpoint GET /home/summary — direction count rollup */
export interface DirectionCounts {
  BUY: number;
  SELL: number;
  "STRONG BUY": number;
  "STRONG SELL": number;
  NEUTRAL: number;
}

/** @endpoint GET /home/summary — info strip below hero cards */
export interface HomeInfoStrip {
  total_pairs: number;
  high_confidence: number;
  direction_counts: DirectionCounts;
  scan_running: boolean;
  scan_last_run: IsoTimestamp | null;
  scan_progress: number;
}

/** @endpoint GET /home/summary — full bundled payload */
export interface HomeSummary {
  timestamp: IsoTimestamp;
  hero_cards: HeroCard[];
  info_strip: HomeInfoStrip;
}

// ─── Regimes ────────────────────────────────────────────────────────────────

/** @endpoint GET /regimes/ — one regime row */
export interface RegimeRow {
  pair: TradingPair;
  regime: RegimeLabel;
  direction: DirectionLabel | string | null;
  confidence: number | null;
}

/** @endpoint GET /regimes/ — full list response */
export interface RegimesList {
  count: number;
  summary: Record<RegimeLabel, number>;
  results: RegimeRow[];
}

/** @endpoint GET /regimes/{pair}/history — segment {state, pct} */
export interface RegimeSegment {
  state: RegimeLabel;
  pct: number;
}

/** @endpoint GET /regimes/{pair}/history */
export interface RegimeHistory {
  pair: TradingPair;
  days: number;
  count: number;
  segments: RegimeSegment[];
}

/** @endpoint GET /regimes/transitions — one transition row */
export interface RegimeTransition {
  pair: TradingPair;
  from: RegimeLabel;
  to: RegimeLabel;
  segment_pct: number;
}

/** @endpoint GET /regimes/transitions */
export interface RegimeTransitions {
  count: number;
  days: number;
  transitions: RegimeTransition[];
}

// ─── On-chain ───────────────────────────────────────────────────────────────

export type OnchainMetricKey =
  | "sopr"
  | "mvrv_z"
  | "net_flow"
  | "whale_activity";

/**
 * @endpoint GET /onchain/dashboard
 * Always-defined `source` field lets the UI render the data-source pill.
 * Per-metric values are nullable when the upstream is unavailable
 * (per the AUDIT-2026-05-02 truthful-empty-state fix in routers/onchain.py).
 */
export interface OnchainDashboard {
  pair: TradingPair;
  sopr: number | null;
  mvrv_z: number | null;
  net_flow: number | null;
  whale_activity: boolean | null;
  source: string;
  error?: string | null;
}

/** @endpoint GET /onchain/{metric} */
export interface OnchainMetric {
  pair: TradingPair;
  metric: OnchainMetricKey;
  value: number | boolean | null;
  source: string;
}

// ─── Alerts ─────────────────────────────────────────────────────────────────

/** @endpoint GET /alerts/configure — one rule */
export interface AlertRule {
  id: string;
  pair: TradingPair;
  condition: string;
  threshold: number;
  channels: string[];
  note?: string | null;
}

/** @endpoint GET /alerts/configure — wrapped list */
export interface AlertRulesList {
  count: number;
  rules: AlertRule[];
}

/** @endpoint POST /alerts/configure — input body */
export interface AlertRuleInput {
  pair: string;
  condition: string;
  threshold: number;
  channels?: string[];
  note?: string | null;
}

/** @endpoint POST /alerts/configure — response */
export interface AlertRuleCreated {
  status: "created";
  rule: AlertRule;
}

/** @endpoint DELETE /alerts/configure/{id} */
export interface AlertRuleDeleted {
  status: "deleted";
  id: string;
  remaining: number;
}

/** @endpoint GET /alerts/log — one history row */
export interface AlertLogRow {
  id?: string | number;
  timestamp?: IsoTimestamp;
  pair?: TradingPair;
  type?: string;
  message?: string;
  channel?: string;
  status?: string;
  [extra: string]: unknown;
}

/** @endpoint GET /alerts/log */
export interface AlertLog {
  count: number;
  alerts: AlertLogRow[];
}

// ─── AI Assistant ───────────────────────────────────────────────────────────

/** @endpoint POST /ai/ask — input body */
export interface AskAiInput {
  pair: string;
  signal: string;
  confidence: number;
  indicators?: Record<string, unknown>;
  question?: string | null;
}

/** @endpoint POST /ai/ask — response */
export interface AskAiResponse {
  pair: TradingPair;
  signal: string;
  text: string;
  source: string;
}

/** @endpoint GET /ai/decisions — one decision row */
export interface AiDecision {
  pair?: TradingPair;
  direction?: DirectionLabel | string;
  confidence_avg_pct?: number | null;
  timestamp?: IsoTimestamp;
  [extra: string]: unknown;
}

/** @endpoint GET /ai/decisions */
export interface AiDecisionsList {
  count: number;
  decisions: AiDecision[];
}

// ─── Settings ───────────────────────────────────────────────────────────────

/** @endpoint GET /settings/ — full snapshot. Sensitive keys redacted. */
export interface SettingsSnapshot {
  trading: Record<string, unknown>;
  signal_risk: Record<string, unknown>;
  dev_tools: Record<string, unknown>;
  execution: Record<string, unknown>;
  all: Record<string, unknown>;
}

/** @endpoint PUT /settings/{group} — generic patch body. Server validates. */
export type SettingsPatch = Record<string, unknown>;

/** @endpoint PUT /settings/{group} — response with rejected-key surface */
export interface SettingsPutResponse {
  status: "ok" | "partial";
  applied: Record<string, unknown>;
  rejected: { key: string; reason: string; value: unknown }[];
  current: Record<string, unknown>;
}

// ─── Exchange ───────────────────────────────────────────────────────────────

/** @endpoint POST /exchange/test-connection */
export interface ExchangeTestConnection {
  ok: boolean;
  balance_usdt: number;
  error: string | null;
}

// ─── Diagnostics ────────────────────────────────────────────────────────────

export type GateStatus = "ok" | "warn" | "breach" | "unmeasured";

/** @endpoint GET /diagnostics/circuit-breakers — one gate row */
export interface CircuitBreakerGate {
  id: number;
  label: string;
  status: GateStatus;
  detail: string;
  value: number | boolean | null;
  limit: number | boolean | null;
}

/** @endpoint GET /diagnostics/circuit-breakers */
export interface CircuitBreakersResponse {
  all_operational: boolean;
  has_unmeasured: boolean;
  gate_count: number;
  gates: CircuitBreakerGate[];
  last_check: IsoTimestamp;
}

/** @endpoint GET /diagnostics/database */
export interface DatabaseHealth {
  tables: {
    feedback_log: number;
    signal_history: number;
    backtest_trades: number;
    paper_trades: number;
    positions: number;
    agent_log: number;
    alerts_log: number;
    execution_log: number;
  };
  backtest_unique_runs: number;
  db_size_kb: number;
  db_size_mb: number;
  wal_mode: boolean;
  auto_vacuum: string;
}

// ─── Execution ──────────────────────────────────────────────────────────────

/** @endpoint GET /execute/status — drives the AGENT pill in topbar */
export interface ExecutionStatus {
  live_trading: boolean;
  keys_configured: boolean;
  agent_running?: boolean;
  paper_balance_usdt?: number;
  open_positions?: number;
  recent_orders?: number;
  [extra: string]: unknown;
}

/** @endpoint POST /execute/order — input body */
export interface PlaceOrderInput {
  pair: string;
  direction: DirectionLabel | string;
  size_usd: number;
  order_type?: "market" | "limit";
  limit_price?: number | null;
  current_price?: number | null;
  client_order_id?: string | null;
}

/** @endpoint POST /execute/order — response (paper or live) */
export interface PlaceOrderResponse {
  ok: boolean;
  mode: "paper" | "live" | "dry_run" | "aborted_emergency_stop";
  pair: TradingPair;
  direction: string;
  side: "buy" | "sell" | null;
  size_usd: number;
  order_type: string;
  price: number | null;
  order_id: string | null;
  error: string | null;
  placed_at: IsoTimestamp;
  slippage_pct?: number | null;
  fee_usd?: number | null;
  effective_usd?: number | null;
  client_order_id?: string | null;
  idempotent_replay?: boolean;
}

// ─── Backtester ─────────────────────────────────────────────────────────────

/** @endpoint GET /backtest/summary */
export interface BacktestSummary {
  total_trades: number;
  win_rate_pct: number | null;
  avg_pnl_pct: number | null;
  max_drawdown_pct: number | null;
  sharpe_ratio: number | null;
  start_date?: IsoTimestamp | null;
  end_date?: IsoTimestamp | null;
  [extra: string]: unknown;
}

/** @endpoint GET /backtest/trades — one row */
export interface BacktestTrade {
  id?: string | number;
  pair?: TradingPair;
  direction?: DirectionLabel | string;
  entry?: number | null;
  exit?: number | null;
  pnl_pct?: number | null;
  pnl_usd?: number | null;
  open_time?: IsoTimestamp | null;
  close_time?: IsoTimestamp | null;
  outcome?: string | null;
  [extra: string]: unknown;
}

/** @endpoint GET /backtest/trades */
export interface BacktestTradesList {
  count: number;
  trades: BacktestTrade[];
}

/** @endpoint GET /backtest/runs — one run summary */
export interface BacktestRun {
  run_id: string | number;
  start_date?: IsoTimestamp | null;
  end_date?: IsoTimestamp | null;
  total_trades?: number;
  win_rate_pct?: number | null;
  [extra: string]: unknown;
}

/** @endpoint GET /backtest/runs */
export interface BacktestRunsList {
  count: number;
  runs: BacktestRun[];
}

/** @endpoint GET /backtest/arbitrage — one arb opportunity row */
export interface ArbitrageOpportunity {
  pair?: TradingPair;
  buy_exchange?: string;
  sell_exchange?: string;
  gross_spread_pct?: number;
  net_spread_pct?: number;
  buy_price?: number;
  sell_price?: number;
  detected_at?: IsoTimestamp;
  [extra: string]: unknown;
}

/** @endpoint GET /backtest/arbitrage */
export interface ArbitrageList {
  count: number;
  opportunities: ArbitrageOpportunity[];
}

// ─── System / health / scan ─────────────────────────────────────────────────

export type HealthStatus = "ok" | "degraded" | "down";

/** @endpoint GET /health — public, no API key required */
export interface HealthResponse {
  status: HealthStatus;
  timestamp: IsoTimestamp;
  db?: Record<string, number>;
  scan?: ScanStatus;
  feeds?: {
    connected: boolean;
    reconnects: number;
    pairs_live: TradingPair[];
  };
  version?: string | null;
  uptime_seconds?: number | null;
  [extra: string]: unknown;
}

/** @endpoint GET /scan/status */
export interface ScanStatus {
  running: boolean;
  timestamp: IsoTimestamp | null;
  error: string | null;
  progress: number;
  pair: string;
}

/** @endpoint POST /scan/trigger */
export interface ScanTriggerResponse {
  status: "started" | "already_running" | "error";
  message?: string;
}

// ─── Error envelope (FastAPI default) ───────────────────────────────────────

/** FastAPI's `HTTPException(detail=...)` body shape */
export interface ApiErrorBody {
  detail: string | { msg: string; type?: string }[] | unknown;
}
