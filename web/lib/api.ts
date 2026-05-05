/**
 * web/lib/api.ts
 *
 * Typed fetch wrappers — one per FastAPI endpoint. Every call goes
 * through `apiFetch` which:
 *   - prepends `NEXT_PUBLIC_API_BASE` to the path
 *   - attaches `X-API-Key: NEXT_PUBLIC_API_KEY` on protected routes
 *   - throws an `ApiError` with the parsed FastAPI `detail` field on
 *     non-2xx responses so React Query's error UI gets useful copy
 *
 * Auth posture (D4 plan §2.4): `NEXT_PUBLIC_API_KEY` is exposed to
 * client bundles. Acceptable trade-off for the D4-D8 window where the
 * only consumer is David. Real auth (NextAuth + JWT) lands post-D8.
 */
import type {
  AlertLog,
  AlertRuleCreated,
  AlertRuleDeleted,
  AlertRuleInput,
  AlertRulesList,
  AskAiInput,
  AskAiResponse,
  AiDecisionsList,
  ArbitrageList,
  BacktestRunsList,
  BacktestSummary,
  BacktestTradesList,
  CircuitBreakersResponse,
  DatabaseHealth,
  ExchangeTestConnection,
  ExecutionStatus,
  HealthResponse,
  HomeSummary,
  OnchainDashboard,
  OnchainMetric,
  OnchainMetricKey,
  PlaceOrderInput,
  PlaceOrderResponse,
  RegimeHistory,
  RegimeTransitions,
  RegimesList,
  ScanStatus,
  ScanTriggerResponse,
  SettingsPatch,
  SettingsPutResponse,
  SettingsSnapshot,
  SignalsList,
  SignalRow,
  TradingPair,
} from "./api-types";

// ─── Environment / constants ────────────────────────────────────────────────

// AUDIT-2026-05-04 (H4 — hardened 2026-05-05): in production builds, a missing
// NEXT_PUBLIC_API_BASE would silently fall back to http://localhost:8000 —
// every page would render as if working but every fetch would CORS-fail to a
// non-existent host. Guard against that — but only in the BROWSER, not during
// Next.js build/prerender. Throwing at module-load during SSR/prerender of the
// /_not-found page broke the production build (verified Vercel build log
// 2026-05-05: "Error occurred prerendering page '/_not-found'"). Move the
// throw behind `typeof window !== "undefined"` so the build succeeds and the
// runtime guard still fires the moment a misconfigured deploy serves a page
// to a real user.
const _RAW_API_BASE = process.env.NEXT_PUBLIC_API_BASE;
if (
  !_RAW_API_BASE &&
  process.env.NODE_ENV === "production" &&
  typeof window !== "undefined"
) {
  throw new Error(
    "NEXT_PUBLIC_API_BASE is not set in this production build. The frontend " +
      "would silently issue cross-origin requests to localhost. Set the env var " +
      "in your Vercel project (Settings → Environment Variables) and redeploy."
  );
}
const API_BASE: string = _RAW_API_BASE ?? "http://localhost:8000";

/** Auth key from build-time env. Empty string = unauth attempt (server
 * will 401 unless CRYPTO_SIGNAL_ALLOW_UNAUTH=true on the API side).
 * AUDIT-2026-05-04 (H4): also warn in production if missing — without
 * the key every protected endpoint returns 401 and the UI looks empty.
 * console.error doesn't break the build, so no browser-gate needed. */
const _RAW_API_KEY = process.env.NEXT_PUBLIC_API_KEY;
if (
  !_RAW_API_KEY &&
  process.env.NODE_ENV === "production" &&
  typeof window !== "undefined"
) {
  // eslint-disable-next-line no-console
  console.error(
    "[api] NEXT_PUBLIC_API_KEY is not set — every protected endpoint will 401. " +
      "Set it in your Vercel project env vars and redeploy."
  );
}
const API_KEY: string = _RAW_API_KEY ?? "";

// ─── Error envelope ─────────────────────────────────────────────────────────

export class ApiError extends Error {
  public readonly status: number;
  public readonly endpoint: string;
  public readonly detail: unknown;

  constructor(status: number, endpoint: string, detail: unknown, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.endpoint = endpoint;
    this.detail = detail;
  }

  /** AUDIT-2026-05-03 (D4 audit, HIGH): try/catch around stringify so
   * a circular-ref `detail` object can't crash the categorizer. */
  private detailText(): string {
    try {
      return JSON.stringify(this.detail).toLowerCase();
    } catch {
      try {
        return String(this.detail).toLowerCase();
      } catch {
        return "";
      }
    }
  }

  /** True for the geo-block category (per D4 plan §6 error taxonomy) */
  get isGeoBlocked(): boolean {
    if (this.status !== 403) return false;
    return /binance.*us|geo[-_ ]?block/.test(this.detailText());
  }

  /** True for the rate-limit category */
  get isRateLimited(): boolean {
    if (this.status === 429) return true;
    return /rate.?limit|too.?many/.test(this.detailText());
  }

  /** True when the API key is missing or rejected */
  get isAuthError(): boolean {
    return this.status === 401 || this.status === 403;
  }
}

// ─── Core fetcher ───────────────────────────────────────────────────────────

interface FetchOptions {
  /** Whether to attach the X-API-Key header. Default true. /health is
   * the one public endpoint where this should be false. */
  authenticated?: boolean;
  /** Optional AbortSignal — TanStack Query passes one for cancellation. */
  signal?: AbortSignal;
  /** HTTP method override. Default GET. */
  method?: "GET" | "POST" | "PUT" | "DELETE";
  /** JSON body for POST/PUT. */
  body?: unknown;
}

async function apiFetch<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const {
    authenticated = true,
    signal,
    method = "GET",
    body,
  } = options;

  const url = `${API_BASE}${path}`;
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (authenticated && API_KEY) {
    headers["X-API-Key"] = API_KEY;
  }
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    });
  } catch (err) {
    // Network / abort / DNS failure — wrap so callers always see ApiError
    const message =
      err instanceof Error ? err.message : "Network error contacting API";
    throw new ApiError(0, path, null, message);
  }

  if (!response.ok) {
    let detail: unknown = null;
    try {
      detail = await response.json();
    } catch {
      try {
        detail = await response.text();
      } catch {
        detail = null;
      }
    }
    // AUDIT-2026-05-03 (D4 audit, MEDIUM): handle the FastAPI
    // validation-error shape `{detail: [{msg, type}, ...]}` so the
    // message doesn't render as "[object Object],[object Object]".
    const message = (() => {
      if (typeof detail === "object" && detail && "detail" in detail) {
        const d = (detail as { detail: unknown }).detail;
        if (Array.isArray(d) && d.length > 0) {
          const first = d[0] as { msg?: unknown; loc?: unknown };
          if (first && typeof first.msg === "string") return first.msg;
        }
        if (typeof d === "string") return d;
        try {
          return JSON.stringify(d);
        } catch {
          return String(d);
        }
      }
      return `${method} ${path} failed with HTTP ${response.status}`;
    })();
    throw new ApiError(response.status, path, detail, message);
  }

  // 204 No Content shortcut
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

// ─── Health + scan (public/system) ─────────────────────────────────────────

export const getHealth = (signal?: AbortSignal) =>
  apiFetch<HealthResponse>("/health", { authenticated: false, signal });

export const getScanStatus = (signal?: AbortSignal) =>
  apiFetch<ScanStatus>("/scan/status", { signal });

export const triggerScan = () =>
  apiFetch<ScanTriggerResponse>("/scan/trigger", { method: "POST" });

// ─── Home ───────────────────────────────────────────────────────────────────

export const getHomeSummary = (heroCount = 5, signal?: AbortSignal) =>
  apiFetch<HomeSummary>(`/home/summary?hero_count=${heroCount}`, { signal });

// ─── Signals ────────────────────────────────────────────────────────────────

export interface GetSignalsParams {
  direction?: string;
  limit?: number;
}

export const getSignals = (
  params: GetSignalsParams = {},
  signal?: AbortSignal,
): Promise<SignalsList> => {
  const qs = new URLSearchParams();
  if (params.direction) qs.set("direction", params.direction);
  if (params.limit !== undefined) qs.set("limit", String(params.limit));
  const tail = qs.toString() ? `?${qs.toString()}` : "";
  return apiFetch<SignalsList>(`/signals${tail}`, { signal });
};

export const getSignalForPair = (pair: TradingPair, signal?: AbortSignal) =>
  apiFetch<SignalRow>(`/signals/${encodeURIComponent(pair)}`, { signal });

// ─── Regimes ────────────────────────────────────────────────────────────────

export const getRegimes = (signal?: AbortSignal) =>
  apiFetch<RegimesList>("/regimes/", { signal });

export const getRegimeHistory = (
  pair: TradingPair,
  days = 90,
  signal?: AbortSignal,
) =>
  apiFetch<RegimeHistory>(
    `/regimes/${encodeURIComponent(pair)}/history?days=${days}`,
    { signal },
  );

export const getRegimeTransitions = (
  days = 30,
  limit = 200,
  signal?: AbortSignal,
) =>
  apiFetch<RegimeTransitions>(
    `/regimes/transitions?days=${days}&limit=${limit}`,
    { signal },
  );

// ─── On-chain ───────────────────────────────────────────────────────────────

export const getOnchainDashboard = (
  pair: TradingPair = "BTC/USDT",
  signal?: AbortSignal,
) =>
  apiFetch<OnchainDashboard>(
    `/onchain/dashboard?pair=${encodeURIComponent(pair)}`,
    { signal },
  );

export const getOnchainMetric = (
  metric: OnchainMetricKey,
  pair: TradingPair = "BTC/USDT",
  signal?: AbortSignal,
) =>
  // AUDIT-2026-05-03 (D4 audit, LOW): encodeURIComponent on `metric`
  // too — defends against future widening of the OnchainMetricKey
  // union to a free-form string.
  apiFetch<OnchainMetric>(
    `/onchain/${encodeURIComponent(metric)}?pair=${encodeURIComponent(pair)}`,
    { signal },
  );

// ─── Alerts ─────────────────────────────────────────────────────────────────

export const getAlertRules = (signal?: AbortSignal) =>
  apiFetch<AlertRulesList>("/alerts/configure", { signal });

export const createAlertRule = (rule: AlertRuleInput) =>
  apiFetch<AlertRuleCreated>("/alerts/configure", { method: "POST", body: rule });

export const deleteAlertRule = (ruleId: string) =>
  apiFetch<AlertRuleDeleted>(
    `/alerts/configure/${encodeURIComponent(ruleId)}`,
    { method: "DELETE" },
  );

export const getAlertLog = (limit = 100, signal?: AbortSignal) =>
  apiFetch<AlertLog>(`/alerts/log?limit=${limit}`, { signal });

// ─── AI Assistant ───────────────────────────────────────────────────────────

export const askAi = (input: AskAiInput) =>
  apiFetch<AskAiResponse>("/ai/ask", { method: "POST", body: input });

export const getAiDecisions = (
  limit = 20,
  pair?: TradingPair,
  signal?: AbortSignal,
) => {
  const qs = new URLSearchParams({ limit: String(limit) });
  if (pair) qs.set("pair", pair);
  return apiFetch<AiDecisionsList>(`/ai/decisions?${qs.toString()}`, { signal });
};

// ─── Settings ───────────────────────────────────────────────────────────────

export const getSettings = (signal?: AbortSignal) =>
  apiFetch<SettingsSnapshot>("/settings/", { signal });

export type SettingsGroup = "trading" | "signal-risk" | "dev-tools" | "execution";

export const putSettings = (group: SettingsGroup, patch: SettingsPatch) =>
  apiFetch<SettingsPutResponse>(`/settings/${group}`, {
    method: "PUT",
    body: patch,
  });

// ─── Exchange ───────────────────────────────────────────────────────────────

export const testExchangeConnection = () =>
  apiFetch<ExchangeTestConnection>("/exchange/test-connection", {
    method: "POST",
  });

// ─── Diagnostics ────────────────────────────────────────────────────────────

export const getCircuitBreakers = (signal?: AbortSignal) =>
  apiFetch<CircuitBreakersResponse>("/diagnostics/circuit-breakers", { signal });

export const getDatabaseHealth = (signal?: AbortSignal) =>
  apiFetch<DatabaseHealth>("/diagnostics/database", { signal });

// ─── Execution ──────────────────────────────────────────────────────────────

export const getExecutionStatus = (signal?: AbortSignal) =>
  // AUDIT-2026-05-03 (D4d contract drift fix): the FastAPI route is
  // `/execute/status` (singular "execute"), not `/execution/status`.
  // The api-contract drift-guard test caught this on the first run
  // — fixing the TS client side to match the live deploy.
  apiFetch<ExecutionStatus>("/execute/status", { signal });

export const placeOrder = (input: PlaceOrderInput) =>
  apiFetch<PlaceOrderResponse>("/execute/order", { method: "POST", body: input });

// ─── Backtester ─────────────────────────────────────────────────────────────

export const getBacktestSummary = (signal?: AbortSignal) =>
  apiFetch<BacktestSummary>("/backtest/summary", { signal });

export const getBacktestTrades = (
  limit = 50,
  offset = 0,
  signal?: AbortSignal,
) =>
  apiFetch<BacktestTradesList>(
    `/backtest/trades?limit=${limit}&offset=${offset}`,
    { signal },
  );

export const getBacktestRuns = (signal?: AbortSignal) =>
  apiFetch<BacktestRunsList>("/backtest/runs", { signal });

export const getBacktestArbitrage = (signal?: AbortSignal) =>
  // TODO(D-ext): /backtest/arbitrage may not be implemented yet on the
  // FastAPI side; if it 404s the consumer hook surfaces an empty list.
  apiFetch<ArbitrageList>("/backtest/arbitrage", { signal });

// ─── Convenience: API_BASE for places that need the bare URL ────────────────

export const apiBase = (): string => API_BASE;
